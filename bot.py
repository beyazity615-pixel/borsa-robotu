"""
bot.py
------
BIST canlı alım-satım / portföy izleme botu — ana giriş noktası.

Kullanım:
    python bot.py                  # Zamanlayıcı modu: seans saatlerinde BIST 100 taraması
                                   # + her Cuma 12:30'da AI portföy görevi
    python bot.py --once          # Tek seferlik anlık BIST 100 taraması
    python bot.py --report        # Günlük özet rapor (Telegram'a gönderilir)
    python bot.py --weekly-ai     # Manuel haftalık AI portföy raporu üretimi
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # başlıksız/sunucu ortamında güvenli render
import matplotlib.pyplot as plt
import schedule

import telegram_notifier
from ai_portfolio_manager import run_friday_job, check_daily_portfolio_changes
from indicators import (
    get_indicators_batch,
    load_finlab_data,
    check_daily_trend,
    load_price_history,
)
from scheduler_manager import (
    is_market_open, is_trading_day, is_friday_afternoon_window,
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
# BIST 100 Sembol Listesi
# --------------------------------------------------------------------------- #
DEFAULT_WATCHLIST = [
    "AGHOL", "AGROT", "AHGAZ", "AKBNK", "AKCNS", "AKFGY", "AKFYE", "AKSA", "AKSEN", "ALARK",
    "ALBRK", "ALFAS", "ANSGR", "ARCLK", "ASELS", "ASTOR", "BERA", "BIENP", "BIMAS", "BINHO",
    "BOBET", "BRSAN", "BRYAT", "BUCIM", "CANTE", "CCOLA", "CIMSA", "CWENE", "DOAS", "DOHOL",
    "EBEBK", "ECILC", "ECZYT", "EGEEN", "EKGYO", "ENJSA", "ENKAI", "EREGL", "EUPWR", "EUREK",
    "FROTO", "GARAN", "GESAN", "GUBRF", "HALKB", "HEKTS", "ISCTR", "ISGYO", "ISMEN", "KAYSE",
    "KCAER", "KCHOL", "KLSER", "KONTR", "KORDS", "KOZAL", "KOZAA", "KRDMD", "MAVI", "MHRGY",
    "MIATK", "MGROS", "ODAS", "OTKAR", "OYAKC", "PETKM", "PGSUS", "PSGYO", "REEDR", "SAHOL",
    "SASA", "SDTTR", "SISE", "SKBNK", "SOKM", "TABGD", "TAVHL", "TCELL", "THYAO", "TKFEN",
    "TOASO", "TSKB", "TTKOM", "TTRAK", "TUPRS", "TURSG", "ULKER", "VAKBN", "VESBE", "VESTL",
    "YEOTK", "YKBNK", "ZOREN"
]

# --------------------------------------------------------------------------- #
# Sinyal filtre eşikleri
# --------------------------------------------------------------------------- #
RSI_MIN, RSI_MAX = 48, 72
VOLUME_MULTIPLIER = 1.3
TV_ALLOWED = {"BUY", "STRONG_BUY", "NEUTRAL"}
FINLAB_MIN_SCORE = 40

_SIGNALED_TODAY: set[str] = set()  # aynı gün tekrar tekrar aynı sinyali göndermemek için


# --------------------------------------------------------------------------- #
# Sinyal mantığı
# --------------------------------------------------------------------------- #
def evaluate_signal(row: dict) -> tuple[bool, list[str]]:
    """
    Spesifikasyondaki 4 adımlı sinyal kontrolünü uygular:
      1) Günlük trend kontrolü
      2) Teknik indikatör şartları (ADX, RSI 48-72, MACD pozitif, Hacim > Vol_SMA20*1.3)
      3) TradingView süzgeci
      4) Finlab süzgeci
    Dönüş: (sinyal_var_mi, gerekce_listesi)
    """
    reasons = []

    # 1) Günlük trend
    if not check_daily_trend(row):
        return False, ["Günlük trend yükseliş yapısında değil (EMA50<=EMA200 veya Close<=EMA50)"]
    reasons.append("✅ Günlük trend yükseliş yapısında (EMA50>EMA200, Close>EMA50)")

    # 2) Teknik indikatör şartları
    adx = row.get("ADX")
    if adx is None or adx < 20:
        return False, reasons + [f"❌ ADX yetersiz ({adx})"]
    reasons.append(f"✅ ADX güçlü trend gösteriyor ({adx:.1f})")

    rsi = row.get("RSI")
    if rsi is None or not (RSI_MIN <= rsi <= RSI_MAX):
        return False, reasons + [f"❌ RSI bant dışında ({rsi})"]
    reasons.append(f"✅ RSI ideal bantta ({rsi:.1f})")

    macd_hist = row.get("MACD_Hist")
    if macd_hist is None or macd_hist <= 0:
        return False, reasons + [f"❌ MACD histogram negatif/eksik ({macd_hist})"]
    reasons.append(f"✅ MACD histogram pozitif ({macd_hist:.3f})")

    volume, vol_sma20 = row.get("Volume"), row.get("Vol_SMA20")
    if vol_sma20 is None:
        reasons.append("⚠️ Vol_SMA20 henüz yeterli geçmiş veri birikmediği için hesaplanamadı, hacim şartı atlandı")
    elif volume is None or volume <= vol_sma20 * VOLUME_MULTIPLIER:
        return False, reasons + [f"❌ Hacim yetersiz ({volume} <= {vol_sma20 * VOLUME_MULTIPLIER:.0f})"]
    else:
        reasons.append(f"✅ Hacim patlaması ({volume:.0f} > {vol_sma20 * VOLUME_MULTIPLIER:.0f})")

    # 3) TradingView süzgeci
    tv_rec = row.get("TV_Recommendation")
    if tv_rec not in TV_ALLOWED:
        return False, reasons + [f"❌ TradingView tavsiyesi uygun değil ({tv_rec})"]
    reasons.append(f"✅ TradingView tavsiyesi: {tv_rec}")

    # 4) Finlab süzgeci
    finlab_score = row.get("Finlab_Score") or 0
    fundamental_ok = row.get("Fundamental_OK")
    if finlab_score < FINLAB_MIN_SCORE or not fundamental_ok:
        return False, reasons + [f"❌ Finlab kriteri sağlanmadı (skor={finlab_score}, uygun={fundamental_ok})"]
    reasons.append(f"✅ Finlab skoru yeterli ({finlab_score}, temel durum uygun)")

    return True, reasons


# --------------------------------------------------------------------------- #
# Grafik üretimi (yerel biriken fiyat geçmişinden)
# --------------------------------------------------------------------------- #
def generate_chart(symbol: str, row: dict) -> Optional[Path]:
    """
    NOT: tradingview-ta geçmiş mum verisi sağlamadığından, grafik botun
    kendi çalıştırıldığı zamanlardan itibaren yerel data/price_history/
    kaydından üretilir.
    """
    hist = load_price_history(symbol)
    fig, ax = plt.subplots(figsize=(8, 4.5))

    if hist is not None and len(hist) >= 2:
        ax.plot(hist["timestamp"], hist["close"], marker="o", linewidth=1.5, color="#1f77b4")
        ax.set_title(f"{symbol} — Yerel Fiyat Geçmişi (bot çalıştırmaları)")
        ax.set_ylabel("Fiyat (TRY)")
        ax.tick_params(axis="x", rotation=30)
    else:
        ax.text(0.5, 0.5, "Yeterli geçmiş veri birikmedi\n(bot yeni çalışmaya başladı)",
                ha="center", va="center", fontsize=11)
        ax.set_title(f"{symbol} — Sinyal Anlık Görüntüsü")
        ax.axis("off")

    info = (f"Close: {row.get('Close')}  |  RSI: {row.get('RSI'):.1f}  |  ADX: {row.get('ADX'):.1f}\n"
            f"TV: {row.get('TV_Recommendation')}  |  Finlab: {row.get('Finlab_Score')}")
    fig.text(0.5, 0.01, info, ha="center", fontsize=9, color="#444444")

    fig.tight_layout(rect=(0, 0.05, 1, 1))
    out_path = CHARTS_DIR / f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M')}.png"
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------- #
# Ana tarama işi
# --------------------------------------------------------------------------- #
def check_market(symbols: Optional[list[str]] = None) -> list[dict]:
    symbols = symbols or DEFAULT_WATCHLIST
    finlab_db = load_finlab_data()
    logger.info("BIST 100 Piyasa taraması başladı (%d sembol)...", len(symbols))

    df = get_indicators_batch(symbols, finlab_db)
    triggered = []

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        symbol = row_dict["Symbol"]
        ok, reasons = evaluate_signal(row_dict)

        if ok and symbol not in _SIGNALED_TODAY:
            logger.info("🚀 SİNYAL: %s", symbol)
            chart_path = None
            try:
                chart_path = generate_chart(symbol, row_dict)
            except Exception as exc:
                logger.error("Grafik üretim hatası (%s): %s", symbol, exc)

            caption = (
                f"🚀 *ALIM SİNYALİ: {symbol}*\n\n"
                f"Fiyat: {row_dict.get('Close')} TRY\n"
                f"RSI: {row_dict.get('RSI'):.1f} | ADX: {row_dict.get('ADX'):.1f}\n"
                f"TradingView: {row_dict.get('TV_Recommendation')}\n"
                f"Finlab Skoru: {row_dict.get('Finlab_Score')}\n\n"
                + "\n".join(reasons)
            )
            if chart_path:
                telegram_notifier.send_photo(chart_path, caption=caption)
            else:
                telegram_notifier.send_message(caption)

            _SIGNALED_TODAY.add(symbol)
            triggered.append(row_dict)
        elif ok:
            logger.info("Sinyal zaten bugün gönderildi, atlanıyor: %s", symbol)
        else:
            logger.debug("%s sinyal vermedi: %s", symbol, reasons[-1] if reasons else "")

    logger.info("Tarama tamamlandı. %d sinyal üretildi.", len(triggered))
    return triggered


# --------------------------------------------------------------------------- #
# Günlük özet rapor
# --------------------------------------------------------------------------- #
def daily_report(symbols: Optional[list[str]] = None) -> str:
    symbols = symbols or DEFAULT_WATCHLIST
    finlab_db = load_finlab_data()
    df = get_indicators_batch(symbols, finlab_db)

    lines = [f"📋 *GÜNLÜK BIST 100 ÖZET RAPORU* — {datetime.now().strftime('%d.%m.%Y %H:%M')}", ""]
    buy_count = 0
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        ok, _ = evaluate_signal(row_dict)
        tag = "🟢 UYGUN" if ok else "⚪️"
        if ok:
            buy_count += 1
        lines.append(
            f"{tag} {row_dict['Symbol']}: Close={row_dict.get('Close')} "
            f"RSI={row_dict.get('RSI'):.1f} TV={row_dict.get('TV_Recommendation')} "
            f"Finlab={row_dict.get('Finlab_Score')}"
        )
    lines.append(f"\nToplam uygun sinyal: {buy_count}/{len(df)}")

    text = "\n".join(lines)
    telegram_notifier.send_message(text)
    return text


# --------------------------------------------------------------------------- #
# Zamanlayıcı işleri
# --------------------------------------------------------------------------- #
def _scheduled_scan_job():
    if not is_market_open():
        logger.debug("Seans kapalı, tarama atlanıyor. (Şu an: %s)", now_tr().strftime("%H:%M %A"))
        return
    check_market()


def _scheduled_weekly_ai_job():
    if not is_friday_afternoon_window():
        return
    logger.info("Cuma 12:30 penceresi — haftalık AI portföy görevi tetikleniyor.")
    run_friday_job()


def _scheduled_daily_change_job():
    if not is_market_open():
        return
    check_daily_portfolio_changes()


def _reset_daily_state_job():
    _SIGNALED_TODAY.clear()
    logger.info("Günlük sinyal önbelleği sıfırlandı.")


def run_scheduler():
    if not acquire_singleton_lock():
        logger.warning("Bot zaten çalışıyor, bu örnek sonlandırılıyor.")
        sys.exit(0)

    logger.info("Zamanlayıcı modu başladı. Seans: 10:00-18:00 (BIST 100) | AI portföy: Cuma 12:30")

    schedule.every(15).minutes.do(_scheduled_scan_job)
    schedule.every(5).minutes.do(_scheduled_weekly_ai_job)
    schedule.every().day.at("10:05").do(_scheduled_daily_change_job)
    schedule.every().day.at("00:05").do(_reset_daily_state_job)

    while True:
        try:
            schedule.run_pending()
        except Exception:
            logger.exception("Zamanlanmış görev sırasında beklenmeyen hata:")
        time.sleep(30)


# --------------------------------------------------------------------------- #
# CLI giriş noktası
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="BIST 100 Algoritmik Ticaret ve Portföy Botu")
    parser.add_argument("--once", action="store_true", help="Tek seferlik anlık BIST 100 taraması yap")
    parser.add_argument("--report", action="store_true", help="Günlük özet raporu üret ve gönder")
    parser.add_argument("--weekly-ai", action="store_true", help="Haftalık AI portföy raporunu manuel üret")
    args = parser.parse_args()

    if args.once:
        check_market()
    elif args.report:
        daily_report()
    elif args.weekly_ai:
        run_friday_job()
    else:
        if not is_trading_day():
            logger.info("Bugün BIST işlem günü değil (hafta sonu/resmi tatil). "
                         "Zamanlayıcı yine de arka planda bekleyecek.")
        run_scheduler()


if __name__ == "__main__":
    main()