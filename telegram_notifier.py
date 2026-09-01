"""
telegram_notifier.py
--------------------
Telegram Bot API üzerinden gün içi al-sat sinyalleri ve grafik bildirimi gönderim modülü.
"""

import os
import json
import logging
import urllib.request
import urllib.parse
import ssl
from pathlib import Path
from typing import Union, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("telegram_notifier")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8718256499:AAG7avZre1V9EzvZmwt7NVYSL_nE-zC052o")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5418216250")


def send_message(message: str, parse_mode: str = "Markdown", bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
    """Telegram API sendMessage uç noktası üzerinden mesaj gönderir."""
    token = bot_token or TELEGRAM_BOT_TOKEN
    cid = chat_id or TELEGRAM_CHAT_ID

    if not token or not cid:
        logger.error("Telegram Bot Token veya Chat ID tanımlanmamış!")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            }
        )
        context = ssl._create_unverified_context()

        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            res = json.loads(response.read().decode('utf-8'))
            if res.get("ok"):
                logger.info("✅ Telegram mesajı başarıyla iletildi.")
                return True
            else:
                logger.error("❌ Telegram API Hatası: %s", res)
                return False
    except Exception as e:
        logger.error("⚠️ Telegram Mesaj Gönderim Hatası: %s", e)
        return False


def send_photo(photo_path: Union[str, Path], caption: str = "", parse_mode: str = "Markdown", bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
    """Telegram API sendPhoto uç noktası üzerinden grafik görseli ve metin gönderir."""
    token = bot_token or TELEGRAM_BOT_TOKEN
    cid = chat_id or TELEGRAM_CHAT_ID

    photo_path = str(photo_path)
    if not os.path.exists(photo_path):
        logger.warning("Gönderilecek grafik görseli bulunamadı: %s. Metin olarak gönderiliyor.", photo_path)
        return send_message(caption, parse_mode=parse_mode, bot_token=token, chat_id=cid)

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"

    try:
        with open(photo_path, "rb") as f:
            photo_data = f.read()

        filename = os.path.basename(photo_path)
        body = []

        body.append(f"--{boundary}\r\n".encode())
        body.append(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{cid}\r\n'.encode())

        body.append(f"--{boundary}\r\n".encode())
        body.append(f'Content-Disposition: form-data; name="parse_mode"\r\n\r\n{parse_mode}\r\n'.encode())

        if caption:
            body.append(f"--{boundary}\r\n".encode())
            body.append(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode('utf-8'))

        body.append(f"--{boundary}\r\n".encode())
        body.append(f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode())
        body.append(f'Content-Type: image/png\r\n\r\n'.encode())
        body.append(photo_data)
        body.append(b'\r\n')

        body.append(f"--{boundary}--\r\n".encode())
        payload = b''.join(body)

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "Mozilla/5.0"
            }
        )
        context = ssl._create_unverified_context()

        with urllib.request.urlopen(req, context=context, timeout=15) as response:
            res = json.loads(response.read().decode('utf-8'))
            if res.get("ok"):
                logger.info("✅ Telegram Grafik & Sinyal Raporu gönderildi.")
                return True
            else:
                logger.error("❌ Telegram Photo API Hatası: %s", res)
                return send_message(caption, parse_mode=parse_mode, bot_token=token, chat_id=cid)
    except Exception as e:
        logger.error("⚠️ Telegram Grafik Gönderim Hatası: %s", e)
        return send_message(caption, parse_mode=parse_mode, bot_token=token, chat_id=cid)


def format_intraday_signal_message(signal_data: dict) -> str:
    """Gün içi al-sat sinyali için Telegram Markdown formatlı rapor şablonu."""
    symbol = signal_data.get("symbol", "BİLİNMİYOR")
    price = signal_data.get("price", 0.0)
    tp = signal_data.get("tp", price * 1.025)
    sl = signal_data.get("sl", price * 0.985)
    tv_rec = signal_data.get("tv_rec", "BUY")
    reason = signal_data.get("reason", "TradingView teknik özet BUY sinyali ve hacim artışı.")

    msg = (
        f"🟢 *BIST 100 GÜN İÇİ AL SİNYALİ*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Hisse:* `{symbol}` | *Anlık Fiyat:* `{price:.2f} TL`\n"
        f"🎯 *Hedef (%2.5):* `{tp:.2f} TL` | 🛡️ *Stop-Loss (%1.5):* `{sl:.2f} TL`\n"
        f"📊 *TradingView Tavsiyesi:* `{tv_rec}`\n"
        f"💡 *Gerekçe:* {reason}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ *Zaman:* Live TradingView BIST Scanner"
    )
    return msg


if __name__ == "__main__":
    test_sig = {
        "symbol": "THYAO",
        "price": 300.00,
        "tp": 307.50,
        "sl": 295.00,
        "tv_rec": "STRONG_BUY",
        "reason": "RSI 54.2, ADX 26.8, Pozitif MACD Momentum ve 1.5x Hacim Artışı"
    }
    m = format_intraday_signal_message(test_sig)
    print(m)
    send_message(m)
