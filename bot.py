"""
bot.py
------
BIST Tüm Hisseler (~540 Hisse) TradingView Paralel Al-Sat Botu — 8-İndikatörlü Matris, Hisse Optimizasyonu ve EOD Tablo Raporu.

Kullanım:
    python bot.py                  # Seans saatlerinde (hafta içi 10:00 - 18:00) BIST 100 watchdog korumalı tarama
    python bot.py --all-stocks    # Tüm BIST hisselerini (~540 Hisse) multithreaded paralel olarak tara
    python bot.py --once          # Tek seferlik anlık BIST taraması
    python bot.py --report        # Günlük özet performans raporu
    python bot.py --eval          # Seans kapanışı backtest değerlendirmesi ve EOD Markdown Tablosu
    python bot.py --test-risk     # Dinamik ATR risk yöneticisi ve sektör filtresini test et
    python bot.py --optimize      # Parametre optimizasyonu
    python bot.py --optimize-stocks # Hisse bazlı geçmiş strateji optimizasyonunu çalıştır
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import schedule

import telegram_notifier
from bist_symbols import DEFAULT_WATCHLIST, get_sector, get_symbol_universe
from indicators import (
    get_indicators_batch,
    check_daily_trend,
    load_price_history,
)
from scheduler_manager import (
    is_market_open, is_trading_day,
    acquire_singleton_lock, now_tr,
)
from risk_manager import (
    calculate_dynamic_levels,
    filter_sector_concentration,
)
from evaluator import (
    record_emitted_signal,
    evaluate_daily_signals,
)
from optimize_params import (
    load_optimized_parameters,
    run_parameter_optimization,
)
from optimizer import (
    load_stock_strategies,
    run_stock_strategy_optimizer,
)
from watchdog import run_with_watchdog

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

BASE_DIR = Path(__file__).parent
CHARTS_DIR = BASE_DIR / "charts"
CHARTS_DIR.mkdir(exist_ok=True)

# Dinamik optimize parametreler & hisse özel stratejiler
PARAMS = load_optimized_parameters()
STOCK_STRATEGIES = load_stock_strategies()

RSI_MIN = PARAMS.get("RSI_MIN", 48)
RSI_MAX = PARAMS.get("RSI_MAX", 72)
ADX_MIN = PARAMS.get("ADX_MIN", 20.0)
VOLUME_MULTIPLIER = PARAMS.get("VOLUME_MULTIPLIER", 1.3)
TV_ALLOWED = set(PARAMS.get("TV_ALLOWED", ["BUY", "STRONG_BUY"]))

_SIGNALED_TODAY: set[str] = set()


# --------------------------------------------------------------------------- #
# 8-İndikatörlü Matris & Hisse Özel Sinyal Değerlendirme
# --------------------------------------------------------------------------- #
def evaluate_signal(row: dict) -> tuple[bool, list[str]]:
    """
    8-İndikatörlü Matris Sinyal Değerlendirmesi:
      1) Günlük Trend (1d): Close > EMA 50
      2) 8-İndikatör Matrisi (RSI, MACD, EMA, ADX, Bollinger, Stochastic, CCI, Ichimoku)
      3) Hisse Özel Optimize Strateji Kuralları
      4) TradingView Tavsiyesi
    """
    reasons = []
    symbol = row.get("Symbol", "")

    # 1) Günlük Trend Kontrolü
    if not check_daily_trend(row):
        return False, ["Günlük trend yükseliş yapısında değil (Daily Close <= Daily EMA50)"]
    reasons.append("✅ Günlük trend pozitif (1d Close > Daily EMA50)")

    # Hisse Özel Strateji Seçimi
    stock_opt = STOCK_STRATEGIES.get(symbol, {})
    strat_type = stock_opt.get("best_strategy", "STANDARD_MOMENTUM")

    # 2) Momentum ve Osilatör Matrisi
    adx = row.get("ADX")
    if adx is None or pd.isna(adx) or adx < ADX_MIN:
        return False, reasons + [f"❌ ADX trend gücü yetersiz ({adx})"]
    reasons.append(f"✅ ADX trend gücü yeterli ({adx:.1f})")

    rsi = row.get("RSI")
    if rsi is None or pd.isna(rsi) or not (RSI_MIN <= rsi <= RSI_MAX):
        return False, reasons + [f"❌ RSI bant dışında ({rsi})"]
    reasons.append(f"✅ RSI ideal bantta ({rsi:.1f})")

    macd_hist = row.get("MACD_Hist")
    if macd_hist is None or pd.isna(macd_hist) or macd_hist <= 0:
        return False, reasons + [f"❌ MACD histogram negatif/nötr ({macd_hist})"]
    reasons.append(f"✅ MACD momentum pozitif ({macd_hist:.3f})")

    # 3) Özel Strateji Kuralları
    if strat_type == "BOLLINGER_RSI":
        bb_middle = row.get("BB_Middle", row.get("Close"))
        if row.get("Close", 0) < bb_middle:
            return False, reasons + ["❌ Bollinger orta bandı altında"]
        reasons.append("✅ Bollinger pozitif bölgede")
    elif strat_type == "STOCH_ICHIMOKU":
        stoch_k = row.get("Stoch_K", 50)
        stoch_d = row.get("Stoch_D", 50)
        if stoch_k <= stoch_d:
            return False, reasons + ["❌ Stochastic kesişimi negatif"]
        reasons.append(f"✅ Stochastic pozitif kesişim (K={stoch_k:.1f})")
    elif strat_type == "CCI_MOMENTUM":
        cci = row.get("CCI", 0)
        if cci < -20:
            return False, reasons + [f"❌ CCI aşırı satım bölgesinde ({cci:.1f})"]
        reasons.append(f"✅ CCI momentum pozitif ({cci:.1f})")

    # 4) TradingView Tavsiye Süzgeci
    tv_rec = row.get("TV_Recommendation", "NEUTRAL")
    if tv_rec not in TV_ALLOWED:
        return False, reasons + [f"❌ TradingView tavsiyesi uygun değil ({tv_rec})"]
    reasons.append(f"✅ TradingView Tavsiyesi: {tv_rec}")

    row["_applied_strategy"] = strat_type
    return True, reasons


# --------------------------------------------------------------------------- #
# Grafik Üretimi
# --------------------------------------------------------------------------- #
def generate_chart(symbol: str, row: dict, entry: float, tp: float, sl: float, tp_pct: float, sl_pct: float) -> Optional[Path]:
    """Sinyal üretilen hissenin 8-indikatörlü grafik görüntüsünü üretir."""
    try:
        hist = load_price_history(symbol)
        fig, ax = plt.subplots(figsize=(8, 4.5))

        if hist is not None and len(hist) >= 2:
            ax.plot(hist["timestamp"], hist["close"], marker="o", linewidth=1.5, color="#1f77b4", label="Fiyat")
            ax.axhline(tp, color="#10b981", linestyle="--", linewidth=1.5, label=f"Dinamik Hedef: {tp:.2f} TL (+%{tp_pct:.1f})")
            ax.axhline(entry, color="#f59e0b", linestyle="-", linewidth=1.5, label=f"Giriş: {entry:.2f} TL")
            ax.axhline(sl, color="#ef4444", linestyle="--", linewidth=1.5, label=f"Dinamik Stop: {sl:.2f} TL (-%{sl_pct:.1f})")
            ax.set_title(f"{symbol} — TradingView 8-İndikatörlü Al-Sat Seviyeleri")
            ax.set_ylabel("Fiyat (TL)")
            ax.tick_params(axis="x", rotation=30)
            ax.legend(loc="upper left")
        else:
            ax.text(0.5, 0.5, f"{symbol} — Giriş: {entry:.2f} TL\nHedef (+%{tp_pct:.1f}): {tp:.2f} TL | Stop (-%{sl_pct:.1f}): {sl:.2f} TL",
                    ha="center", va="center", fontsize=11)
            ax.set_title(f"{symbol} — Dinamik Al Sinyali")
            ax.axis("off")

        info = (f"Son Fiyat: {entry:.2f} TL  |  RSI: {row.get('RSI'):.1f}  |  ADX: {row.get('ADX'):.1f}\n"
                f"Strateji: {row.get('_applied_strategy', 'STANDARD')}  |  TradingView: {row.get('TV_Recommendation')}")
        fig.text(0.5, 0.01, info, ha="center", fontsize=9, color="#444444")

        fig.tight_layout(rect=(0, 0.05, 1, 1))
        out_path = CHARTS_DIR / f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M')}.png"
        fig.savefig(out_path, dpi=130)
        plt.close(fig)
        return out_path
    except Exception as exc:
        logger.error(f"[{symbol}] Grafik üretimi hatası: {exc}")
        return None


# --------------------------------------------------------------------------- #
# Canlı Tarama Fonksiyonu (Tüm BIST Hisseleri Paralel Tarama)
# --------------------------------------------------------------------------- #
def check_market(symbols: Optional[list[str]] = None) -> list[dict]:
    symbols = symbols or DEFAULT_WATCHLIST
    logger.info("⚡ TradingView Multithreaded Paralel Piyasa Taraması Başladı (%d Hisse)...", len(symbols))

    df = get_indicators_batch(symbols)
    if df.empty:
        logger.warning("TradingView verisi çekilemedi veya veri kümesi boş.")
        return []

    candidates = []

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        symbol = row_dict["Symbol"]
        ok, reasons = evaluate_signal(row_dict)

        if ok and symbol not in _SIGNALED_TODAY:
            row_dict["_reasons"] = reasons
            candidates.append(row_dict)

    # Dinamik Sektör Korelasyon Filtresi
    filtered_signals = filter_sector_concentration(candidates, max_per_sector=1)
    triggered = []

    for row_dict in filtered_signals:
        symbol = row_dict["Symbol"]
        close_price = row_dict.get("Close", 0.0)
        atr_val = row_dict.get("ATR")

        if close_price <= 0:
            continue

        # Dinamik ATR Seviyeleri Hesapla
        tp_price, sl_price, tp_pct, sl_pct = calculate_dynamic_levels(close_price, atr_val)

        logger.info("🚀 GÜN İÇİ AL SİNYALİ: %s (%s) | Fiyat: %.2f TL | TP: %.2f TL (+%%%.1f) | SL: %.2f TL (-%%%.1f)",
                    symbol, get_sector(symbol), close_price, tp_price, tp_pct, sl_price, sl_pct)

        chart_path = None
        try:
            chart_path = generate_chart(symbol, row_dict, close_price, tp_price, sl_price, tp_pct, sl_pct)
        except Exception as exc:
            logger.error("Grafik üretim hatası (%s): %s", symbol, exc)

        signal_payload = {
            "symbol": symbol,
            "price": close_price,
            "tp": tp_price,
            "sl": sl_price,
            "tp_pct": tp_pct,
            "sl_pct": sl_pct,
            "rsi": row_dict.get("RSI"),
            "adx": row_dict.get("ADX"),
            "tv_rec": row_dict.get("TV_Recommendation"),
            "sector": get_sector(symbol),
            "strategy": row_dict.get("_applied_strategy", "8-Indicator Matrix"),
            "reason": row_dict.get("_reasons", ["TradingView al sinyali"])[-1]
        }

        # Backtest Geri Besleme Günlüğüne Kaydet
        record_emitted_signal(signal_payload)

        caption = telegram_notifier.format_intraday_signal_message(signal_payload)

        if chart_path and os.path.exists(chart_path):
            telegram_notifier.send_photo(chart_path, caption=caption)
        else:
            telegram_notifier.send_message(caption)

        _SIGNALED_TODAY.add(symbol)
        triggered.append(signal_payload)

    logger.info("Tarama tamamlandı. %d adet risk kontrollü sinyal üretildi.", len(triggered))
    return triggered


# --------------------------------------------------------------------------- #
# Günlük Özet Rapor
# --------------------------------------------------------------------------- #
def daily_report(symbols: Optional[list[str]] = None) -> str:
    symbols = symbols or DEFAULT_WATCHLIST
    df = get_indicators_batch(symbols)

    lines = [f"📊 *BIST GÜN İÇİ GÜNLÜK ÖZET RAPORU* — {datetime.now().strftime('%d.%m.%Y %H:%M')}", ""]
    buy_count = 0

    if not df.empty:
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            ok, _ = evaluate_signal(row_dict)
            tag = "🟢 AL" if ok else "⚪️ NÖTR"
            if ok:
                buy_count += 1
            
            close = row_dict.get("Close", 0.0)
            tp, sl, tp_pct, sl_pct = calculate_dynamic_levels(close, row_dict.get("ATR"))

            lines.append(
                f"{tag} *{row_dict['Symbol']}*: Fiyat=`{close:.2f} TL` "
                f"TP=`{tp:.2f}` (+%{tp_pct:.1f}) SL=`{sl:.2f}` (-%{sl_pct:.1f}) "
                f"RSI=`{row_dict.get('RSI'):.1f}` TV=`{row_dict.get('TV_Recommendation')}`"
            )
        lines.append(f"\nToplam Uygun Gün İçi Sinyal: {buy_count}/{len(df)}")
    else:
        lines.append("⚠️ Veri çekilemedi.")

    text = "\n".join(lines)
    telegram_notifier.send_message(text)
    return text


# --------------------------------------------------------------------------- #
# Zamanlayıcı Görevleri
# --------------------------------------------------------------------------- #
def _scheduled_scan_job():
    if not is_market_open():
        logger.debug("BIST Seansı kapalı (10:00 - 18:00 arası açık). Tarama atlanıyor.")
        return
    check_market(get_symbol_universe(all_stocks=True))


def _scheduled_market_close_eval_job():
    logger.info("🏁 Seans Kapanışı (18:15) — Gün sonu backtest değerlendirmesi ve Telegram tablosu gönderiliyor...")
    evaluate_daily_signals(scanned_count=len(get_symbol_universe(all_stocks=True)))


def _reset_daily_state_job():
    _SIGNALED_TODAY.clear()
    logger.info("Günlük sinyal önbelleği sıfırlandı.")


def start_bot_engine():
    if not acquire_singleton_lock():
        logger.warning("Bot zaten başka bir süreçte çalışıyor. Yeni süreç sonlandırıldı.")
        sys.exit(0)

    logger.info("🤖 BIST Tüm Hisseler (~540 Hisse) Multithreaded Al-Sat Botu Başlatıldı.")
    logger.info("⏰ Seans Saatleri: Hafta İçi 10:00 - 18:00 (Europe/Istanbul)")

    # Her 15 dakikada bir tüm BIST hisselerini paralel tara
    schedule.every(15).minutes.do(_scheduled_scan_job)
    schedule.every().day.at("18:15").do(_scheduled_market_close_eval_job)
    schedule.every().day.at("00:05").do(_reset_daily_state_job)

    while True:
        try:
            schedule.run_pending()
        except Exception as exc:
            logger.exception("Zamanlanmış görev hatası: %s", exc)
        time.sleep(15)


# --------------------------------------------------------------------------- #
# CLI Giriş Noktası
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="BIST Tüm Hisseler TradingView Otonom Botu")
    parser.add_argument("--all-stocks", action="store_true", help="Tüm BIST hisselerini (~540 Hisse) tara")
    parser.add_argument("--once", action="store_true", help="Tek seferlik anlık BIST taraması yap")
    parser.add_argument("--report", action="store_true", help="Günlük özet performans raporunu gönder")
    parser.add_argument("--eval", action="store_true", help="Seans kapanışı backtest değerlendirmesi ve EOD Telegram tablosunu çalıştır")
    parser.add_argument("--test-risk", action="store_true", help="Dinamik ATR risk yöneticisi ve sektör filtresini test et")
    parser.add_argument("--optimize", action="store_true", help="Strateji parametre optimizasyonunu çalıştır")
    parser.add_argument("--optimize-stocks", action="store_true", help="Hisse bazlı geçmiş strateji optimizasyonunu çalıştır")
    args = parser.parse_args()

    symbols = get_symbol_universe(all_stocks=args.all_stocks)

    if args.once:
        check_market(symbols)
    elif args.report:
        daily_report(symbols)
    elif args.eval:
        evaluate_daily_signals(scanned_count=len(symbols))
    elif args.test_risk:
        print("\n🧪 --- DİNAMİK RİSK YÖNETİCİSİ VE SEKTÖR FİLTRESİ TESTİ ---")
        tp, sl, tp_p, sl_p = calculate_dynamic_levels(100.0, 2.5)
        print(f"Fiyat: 100.00 TL | ATR: 2.50 -> Dynamic TP: {tp} TL (+%{tp_p:.2f}) | SL: {sl} TL (-%{sl_p:.2f})")
    elif args.optimize:
        run_parameter_optimization()
    elif args.optimize_stocks:
        run_stock_strategy_optimizer()
    else:
        if not is_trading_day():
            logger.info("Bugün BIST işlem günü değil (hafta sonu / resmi tatil). Zamanlayıcı beklemede.")
        run_with_watchdog(start_bot_engine)


if __name__ == "__main__":
    main()