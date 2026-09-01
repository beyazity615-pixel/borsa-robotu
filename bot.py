"""
bot.py
------
BIST 100 TradingView Entegre Gün İçi Al-Sat Botu — Ana Giriş Noktası.

Kullanım:
    python bot.py                  # Seans saatlerinde (hafta içi 10:00 - 18:00) periyodik canlı tarama
    python bot.py --once          # Tek seferlik anlık BIST 100 taraması
    python bot.py --report        # Günlük özet performans raporu (Telegram'a gönderilir)
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
from typing import Optional

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import schedule

import telegram_notifier
from bist_symbols import DEFAULT_WATCHLIST, get_sector
from indicators import (
    get_indicators_batch,
    check_daily_trend,
    load_price_history,
)
from scheduler_manager import (
    is_market_open, is_trading_day,
    acquire_singleton_lock, now_tr,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

BASE_DIR = Path(__file__).parent
CHARTS_DIR = BASE_DIR / "charts"
CHARTS_DIR.mkdir(exist_ok=True)

# --------------------------------------------------------------------------- #
# Gün içi al-sat sinyal filtre eşikleri
# --------------------------------------------------------------------------- #
RSI_MIN, RSI_MAX = 48, 72
ADX_MIN = 20.0
VOLUME_MULTIPLIER = 1.3
TV_ALLOWED = {"BUY", "STRONG_BUY"}

TARGET_TP_PCT = 0.025   # %2.5 Kâr Hedefi
STOP_LOSS_PCT = 0.015   # %1.5 Stop-Loss

_SIGNALED_TODAY: set[str] = set()


# --------------------------------------------------------------------------- #
# Gün içi al-sat sinyal değerlendirme mantığı
# --------------------------------------------------------------------------- #
def evaluate_signal(row: dict) -> tuple[bool, list[str]]:
    """
    Intraday Day Trading Sinyal Kontrolü:
      1) Günlük Trend (1d): Close > EMA 50
      2) Momentum: ADX >= 20, RSI 48-72, MACD Histogram > 0
      3) TradingView Tavsiyesi: STRONG_BUY veya BUY
      4) Hacim kontrolü (varsa Vol_SMA20 * 1.3)
    Dönüş: (sinyal_var_mi, gerekce_listesi)
    """
    reasons = []

    # 1) Günlük Trend Kontrolü
    if not check_daily_trend(row):
        return False, ["Günlük trend yükseliş yapısında değil (Daily Close <= Daily EMA50)"]
    reasons.append("✅ Günlük trend pozitif (1d Close > Daily EMA50)")

    # 2) Momentum ve Osilatör Kontrolleri
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

    # 3) Hacim Kontrolü
    volume, vol_sma20 = row.get("Volume"), row.get("Vol_SMA20")
    if vol_sma20 is None or pd.isna(vol_sma20):
        reasons.append("⚠️ Vol_SMA20 henüz yeterli geçmiş veri olmadığı için atlandı")
    elif volume is None or pd.isna(volume) or volume < vol_sma20 * VOLUME_MULTIPLIER:
        return False, reasons + [f"❌ Hacim yetersiz ({volume:.0f} < {vol_sma20 * VOLUME_MULTIPLIER:.0f})"]
    else:
        reasons.append(f"✅ Hacim artışı var ({volume:.0f} >= {vol_sma20 * VOLUME_MULTIPLIER:.0f})")

    # 4) TradingView Tavsiye Süzgeci
    tv_rec = row.get("TV_Recommendation", "NEUTRAL")
    if tv_rec not in TV_ALLOWED:
        return False, reasons + [f"❌ TradingView tavsiyesi uygun değil ({tv_rec})"]
    reasons.append(f"✅ TradingView Tavsiyesi: {tv_rec}")

    return True, reasons


# --------------------------------------------------------------------------- #
# Grafik Üretimi
# --------------------------------------------------------------------------- #
def generate_chart(symbol: str, row: dict, entry: float, tp: float, sl: float) -> Optional[Path]:
    """Sinyal üretilen hissenin fiyat anlık görüntüsü ve seviye grafiğini üretir."""
    try:
        hist = load_price_history(symbol)
        fig, ax = plt.subplots(figsize=(8, 4.5))

        if hist is not None and len(hist) >= 2:
            ax.plot(hist["timestamp"], hist["close"], marker="o", linewidth=1.5, color="#1f77b4", label="Fiyat")
            ax.axhline(tp, color="#10b981", linestyle="--", linewidth=1.5, label=f"Hedef: {tp:.2f} TL (+%2.5)")
            ax.axhline(entry, color="#f59e0b", linestyle="-", linewidth=1.5, label=f"Giriş: {entry:.2f} TL")
            ax.axhline(sl, color="#ef4444", linestyle="--", linewidth=1.5, label=f"Stop: {sl:.2f} TL (-%1.5)")
            ax.set_title(f"{symbol} — TradingView Gün İçi Al-Sat Sinyal Seviyeleri")
            ax.set_ylabel("Fiyat (TL)")
            ax.tick_params(axis="x", rotation=30)
            ax.legend(loc="upper left")
        else:
            ax.text(0.5, 0.5, f"{symbol} — Giriş: {entry:.2f} TL\nHedef (+2.5%): {tp:.2f} TL | Stop (-1.5%): {sl:.2f} TL",
                    ha="center", va="center", fontsize=11)
            ax.set_title(f"{symbol} — Gün İçi Al Sinyali")
            ax.axis("off")

        info = (f"Son Fiyat: {entry:.2f} TL  |  RSI: {row.get('RSI'):.1f}  |  ADX: {row.get('ADX'):.1f}\n"
                f"TradingView: {row.get('TV_Recommendation')}  |  Sektör: {get_sector(symbol)}")
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
# Canlı Tarama Fonksiyonu
# --------------------------------------------------------------------------- #
def check_market(symbols: Optional[list[str]] = None) -> list[dict]:
    symbols = symbols or DEFAULT_WATCHLIST
    logger.info("BIST 100 TradingView canlı piyasa taraması başladı (%d hisse)...", len(symbols))

    df = get_indicators_batch(symbols)
    if df.empty:
        logger.warning("TradingView verisi çekilemedi veya veri kümesi boş.")
        return []

    triggered = []

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        symbol = row_dict["Symbol"]
        ok, reasons = evaluate_signal(row_dict)

        if ok and symbol not in _SIGNALED_TODAY:
            close_price = row_dict.get("Close", 0.0)
            if close_price <= 0:
                continue

            # Target TP (+2.5%) & Stop Loss (-1.5%)
            tp_price = close_price * (1 + TARGET_TP_PCT)
            sl_price = close_price * (1 - STOP_LOSS_PCT)

            logger.info("🚀 GÜN İÇİ AL SİNYALİ: %s | Fiyat: %.2f TL | TP: %.2f TL | SL: %.2f TL",
                        symbol, close_price, tp_price, sl_price)

            chart_path = None
            try:
                chart_path = generate_chart(symbol, row_dict, close_price, tp_price, sl_price)
            except Exception as exc:
                logger.error("Grafik üretim hatası (%s): %s", symbol, exc)

            caption = (
                f"🟢 *BIST 100 GÜN İÇİ AL SİNYALİ*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 *Hisse:* `{symbol}` | *Anlık Fiyat:* `{close_price:.2f} TL`\n"
                f"🎯 *Hedef (%2.5):* `{tp_price:.2f} TL`\n"
                f"🛡️ *Stop-Loss (%1.5):* `{sl_price:.2f} TL`\n"
                f"📊 *TradingView Tavsiyesi:* `{row_dict.get('TV_Recommendation')}`\n"
                f"💡 *Gerekçe:* {reasons[-1] if reasons else 'TradingView al sinyali'}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ *Zaman:* Live TradingView BIST Scanner"
            )

            if chart_path and os.path.exists(chart_path):
                telegram_notifier.send_photo(chart_path, caption=caption)
            else:
                telegram_notifier.send_message(caption)

            _SIGNALED_TODAY.add(symbol)
            row_dict["TP"] = tp_price
            row_dict["SL"] = sl_price
            triggered.append(row_dict)

    logger.info("Tarama tamamlandı. %d sinyal üretildi.", len(triggered))
    return triggered


# --------------------------------------------------------------------------- #
# Günlük Özet Rapor
# --------------------------------------------------------------------------- #
def daily_report(symbols: Optional[list[str]] = None) -> str:
    symbols = symbols or DEFAULT_WATCHLIST
    df = get_indicators_batch(symbols)

    lines = [f"📊 *BIST 100 GÜN İÇİ GÜNLÜK ÖZET RAPORU* — {datetime.now().strftime('%d.%m.%Y %H:%M')}", ""]
    buy_count = 0

    if not df.empty:
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            ok, _ = evaluate_signal(row_dict)
            tag = "🟢 AL" if ok else "⚪️ NÖTR"
            if ok:
                buy_count += 1
            
            close = row_dict.get("Close", 0.0)
            tp = close * (1 + TARGET_TP_PCT)
            sl = close * (1 - STOP_LOSS_PCT)

            lines.append(
                f"{tag} *{row_dict['Symbol']}*: Fiyat=`{close:.2f} TL` "
                f"TP=`{tp:.2f}` SL=`{sl:.2f}` "
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
    check_market()


def _reset_daily_state_job():
    _SIGNALED_TODAY.clear()
    logger.info("Günlük sinyal önbelleği sıfırlandı.")


def run_scheduler():
    if not acquire_singleton_lock():
        logger.warning("Bot zaten başka bir süreçte çalışıyor. Yeni süreç sonlandırıldı.")
        sys.exit(0)

    logger.info("🤖 BIST 100 TradingView Gün İçi Al-Sat Botu Başlatıldı.")
    logger.info("⏰ Seans Saatleri: Hafta İçi 10:00 - 18:00 (Europe/Istanbul)")

    # Her 15 dakikada bir piyasayı tara
    schedule.every(15).minutes.do(_scheduled_scan_job)
    schedule.every().day.at("00:05").do(_reset_daily_state_job)

    while True:
        try:
            schedule.run_pending()
        except Exception:
            logger.exception("Zamanlanmış görev hatası:")
        time.sleep(15)


# --------------------------------------------------------------------------- #
# CLI Giriş Noktası
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="BIST 100 TradingView Gün İçi Al-Sat Botu")
    parser.add_argument("--once", action="store_true", help="Tek seferlik anlık BIST 100 taraması yap")
    parser.add_argument("--report", action="store_true", help="Günlük özet performans raporunu gönder")
    args = parser.parse_args()

    if args.once:
        check_market()
    elif args.report:
        daily_report()
    else:
        if not is_trading_day():
            logger.info("Bugün BIST işlem günü değil (hafta sonu / resmi tatil). Zamanlayıcı beklemede.")
        run_scheduler()


if __name__ == "__main__":
    main()