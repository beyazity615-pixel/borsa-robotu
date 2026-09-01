"""
evaluator.py
============
Gün Sonu Backtest ve Performans Geri Besleme (Feedback Loop) Değerlendirme Modülü.

Özellikler:
1. Seans Kapanışında (saat 18:15) tüm BIST hisseleri için üretilen sinyalleri BIST kapanış fiyatları ile karşılaştırma.
2. İşlemleri WIN, LOSS veya EOD_CLOSE olarak etiketleme ve data/performance_log.json dosyasına işleme.
3. Telegram'a sütunları kusursuz hizalanmış Markdown tablosu halinde seans özet raporunu iletme.
"""

import sys
import io
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from indicators import get_indicators_batch
from bist_symbols import get_symbol_universe
from telegram_notifier import send_message

logger = logging.getLogger("evaluator")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

SIGNALS_LOG_FILE = DATA_DIR / "signals_log.json"
PERFORMANCE_LOG_FILE = DATA_DIR / "performance_log.json"


def load_signals_log() -> List[Dict[str, Any]]:
    if SIGNALS_LOG_FILE.exists():
        try:
            with open(SIGNALS_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Sinyal günlüğü okuma hatası: %s", e)
    return []


def save_signals_log(signals: List[Dict[str, Any]]):
    try:
        with open(SIGNALS_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error("Sinyal günlüğü kaydetme hatası: %s", e)


def load_performance_log() -> List[Dict[str, Any]]:
    if PERFORMANCE_LOG_FILE.exists():
        try:
            with open(PERFORMANCE_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Performans günlüğü okuma hatası: %s", e)
    return []


def save_performance_log(perf: List[Dict[str, Any]]):
    try:
        with open(PERFORMANCE_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(perf, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error("Performans günlüğü kaydetme hatası: %s", e)


def record_emitted_signal(signal_data: Dict[str, Any]):
    """Üretilen canlı sinyali signals_log.json dosyasına ekler."""
    signals = load_signals_log()
    record = {
        "id": f"{signal_data.get('symbol')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "symbol": signal_data.get("symbol"),
        "entry_price": float(signal_data.get("price", 0.0)),
        "tp_price": float(signal_data.get("tp", 0.0)),
        "sl_price": float(signal_data.get("sl", 0.0)),
        "rsi": float(signal_data.get("rsi", 50.0)),
        "adx": float(signal_data.get("adx", 20.0)),
        "tv_rec": signal_data.get("tv_rec", "BUY"),
        "sector": signal_data.get("sector", "Diğer"),
        "status": "OPEN"
    }
    signals.append(record)
    save_signals_log(signals)
    logger.info("📌 Sinyal günlüğüne kaydedildi: %s", record['id'])


def format_eod_table_report(summary: Dict[str, Any]) -> str:
    """Seans sonu hizalanmış Markdown tablosu halinde Telegram rapor metnini oluşturur."""
    scanned_count = summary.get("scanned_count", 540)
    total_signals = summary.get("total_signals", 0)
    wins = summary.get("wins", 0)
    losses = summary.get("losses", 0)
    win_rate = summary.get("win_rate", 0.0)
    trades = summary.get("evaluated_trades", [])

    lines = [
        "📊 *BİST GÜNÜN ÖZETİ & SEANS RAPORU*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔹 *Taranan Hisse:* `{scanned_count}` | *Üretilen Sinyal:* `{total_signals}`",
        f"🎯 *Hedefe Ulaşan (TP):* `{wins}` | *Stop Olan (SL):* `{losses}`",
        f"📈 *Günlük Kümülatif Başarı:* `%{win_rate:.1f}`",
        "",
        "📋 *İşlem Detay Tablosu:*",
        "```text",
        f"{'Hisse':<6} | {'Giriş':<6} | {'Hedef':<6} | {'Sonuç':<5} | {'Getiri':<6}",
        "──────┼────────┼────────┼───────┼───────"
    ]

    if not trades:
        lines.append(f"{'YOK':<6} | {'0.00':<6} | {'0.00':<6} | {'-':<5} | {'%0.0':<6}")
    else:
        for t in trades:
            sym = str(t.get("symbol", ""))[:6]
            entry = f"{t.get('entry', 0.0):.2f}"
            tp = f"{t.get('tp', 0.0):.2f}"
            status = str(t.get("status", "EOD"))[:5]
            ret_val = t.get("net_return_pct", 0.0)
            ret_str = f"+%{ret_val:.1f}" if ret_val >= 0 else f"-%{abs(ret_val):.1f}"

            lines.append(f"{sym:<6} | {entry:<6} | {tp:<6} | {status:<5} | {ret_str:<6}")

    lines.append("```")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 _Öz-İyileştirmeli Al-Sat Botu Seans Raporu_")

    return "\n".join(lines)


def evaluate_daily_signals(scanned_count: int = 540) -> Dict[str, Any]:
    """
    Seans kapanışında (18:15) açık sinyalleri BIST kapanış fiyatları ile
    karşılaştırıp WIN, LOSS veya EOD_CLOSE olarak değerlendirir.
    """
    signals = load_signals_log()
    today_str = datetime.now().strftime("%Y-%m-%d")
    open_signals = [s for s in signals if s.get("status") == "OPEN" or s.get("date") == today_str]

    if not open_signals:
        logger.info("Değerlendirilecek açık sinyal bulunamadı.")
        summary = {
            "date": today_str,
            "scanned_count": scanned_count,
            "total_signals": 0,
            "wins": 0,
            "losses": 0,
            "eod_closes": 0,
            "win_rate": 0.0,
            "net_return": 0.0,
            "evaluated_trades": []
        }
        report_msg = format_eod_table_report(summary)
        send_message(report_msg)
        return summary

    symbols = list(set([s["symbol"] for s in open_signals]))
    logger.info("Gün sonu backtest değerlendirmesi yapılıyor (%d hisse)...", len(symbols))

    df_latest = get_indicators_batch(symbols)
    latest_prices = {}
    if not df_latest.empty:
        for _, r in df_latest.iterrows():
            latest_prices[r["Symbol"]] = float(r["Close"])

    perf_history = load_performance_log()
    evaluated_trades = []

    wins, losses, eod_closes = 0, 0, 0
    total_net_return = 0.0

    for s in open_signals:
        sym = s["symbol"]
        entry = s["entry_price"]
        tp = s["tp_price"]
        sl = s["sl_price"]
        eod_close = latest_prices.get(sym, entry)

        if eod_close >= tp:
            result_status = "WIN"
            ret_pct = ((tp - entry) / entry) * 100
            wins += 1
        elif eod_close <= sl:
            result_status = "LOSS"
            ret_pct = ((sl - entry) / entry) * 100
            losses += 1
        else:
            result_status = "EOD_CLOSE"
            ret_pct = ((eod_close - entry) / entry) * 100
            eod_closes += 1

        total_net_return += ret_pct
        s["status"] = result_status
        s["eod_close_price"] = eod_close
        s["net_return_pct"] = round(ret_pct, 2)

        trade_record = {
            "date": s["date"],
            "symbol": sym,
            "entry": entry,
            "eod_close": eod_close,
            "tp": tp,
            "sl": sl,
            "status": result_status,
            "net_return_pct": round(ret_pct, 2),
            "rsi": s.get("rsi"),
            "adx": s.get("adx"),
            "tv_rec": s.get("tv_rec")
        }
        evaluated_trades.append(trade_record)
        perf_history.append(trade_record)

    save_signals_log(signals)
    save_performance_log(perf_history)

    total_trades = len(evaluated_trades)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

    summary = {
        "date": today_str,
        "scanned_count": scanned_count,
        "total_signals": total_trades,
        "wins": wins,
        "losses": losses,
        "eod_closes": eod_closes,
        "win_rate": round(win_rate, 2),
        "net_return": round(total_net_return, 2),
        "evaluated_trades": evaluated_trades
    }

    # Telegram Kapsamlı Özet Tablosu
    report_msg = format_eod_table_report(summary)
    send_message(report_msg)
    return summary


if __name__ == "__main__":
    res = evaluate_daily_signals()
    print("Gün Sonu Rapor Metni:\n", format_eod_table_report(res))
