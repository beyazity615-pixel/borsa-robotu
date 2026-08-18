import os
import time
import threading
import requests
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from flask import Flask

# .env dosyasından değişkenleri yükle
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 1. RENDER İÇİN FLASK SUNUCUSU ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Borsa Botu 7/24 Canli ve Aktif!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Flask'ı arka planda (thread) çalıştır
threading.Thread(target=run_flask, daemon=True).start()


# --- 2. TELEGRAM BİLDİRİM FONKSİYONU ---
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Hata: TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ayarlanmamış!")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Telegram mesaj gönderme hatası: {response.text}")
    except Exception as e:
        print(f"Telegram bağlantı hatası: {e}")


# --- 3. BİST 100 TARAMA BOTU ---
BIST_100_SYMBOLS = [
    "AKBNK.IS", "ARCLK.IS", "ASELS.IS", "BIMAS.IS", "DOHOL.IS", "EKGYO.IS", "ENKAI.IS", "EREGL.IS",
    "FROTO.IS", "GARAN.IS", "GUBRF.IS", "HEKTS.IS", "ISCTR.IS", "KCHOL.IS", "KOZAL.IS", "KRDMD.IS",
    "PETKM.IS", "PGSUS.IS", "SAHOL.IS", "SASA.IS", "SISE.IS", "TCELL.IS", "THYAO.IS", "TKFEN.IS",
    "TOASO.IS", "TSKB.IS", "TTKOM.IS", "TUPRS.IS", "VAKBN.IS", "YKBNK.IS", "ALBRK.IS", "ANSGR.IS",
    "ASTOR.IS", "BRSAN.IS", "ENJSA.IS", "EUPWR.IS", "GESAN.IS", "ISGYO.IS", "KCAER.IS", "OYAKC.IS",
    "SAYAS.IS", "SOKM.IS", "TABGD.IS", "TAVHL.IS"
]

def scan_market():
    print("Market taraması başlatılıyor...")
    signals_found = 0
    
    for symbol in BIST_100_SYMBOLS:
        try:
            df = yf.download(symbol, period="1mo", interval="1d", progress=False)
            if df.empty or len(df) < 10:
                continue
            
            # Son fiyat ve basit analiz örneği
            last_close = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2])
            change_pct = ((last_close - prev_close) / prev_close) * 100
            
            # Örnek Sinyal Şartı (%2'den fazla yükselenler)
            if change_pct >= 2.0:
                clean_symbol = symbol.replace(".IS", "")
                tp_price = last_close * 1.04   # %4 Kar Al
                sl_price = last_close * 0.975  # %2.5 Stop Loss
                
                msg = (
                    f"🚀 **YENİ ALIM SİNYALİ: #{clean_symbol}**\n\n"
                    f"📈 **Giriş Fiyatı:** {last_close:.2f} TL (+%{change_pct:.2f})\n"
                    f"🎯 **Hedef (TP %4):** {tp_price:.2f} TL\n"
                    f"🛡️ **Stop (SL %2.5):** {sl_price:.2f} TL\n\n"
                    f"⏰ *Zaman:* Live BIST Scanner"
                )
                send_telegram_message(msg)
                print(f"Sinyal Gönderildi: {clean_symbol}")
                signals_found += 1
                
        except Exception as e:
            print(f"Hata ({symbol}): {e}")
            
    print(f"Tarama tamamlandı. {signals_found} adet sinyal bulundu.")

def main():
    send_telegram_message("🤖 *Borsa Robotu Render üzerinde 7/24 canlıya alındı ve aktif!*")
    while True:
        scan_market()
        print("1 saat bekleniyor...")
        time.sleep(3600)  # Her 1 saatte bir piyasayı tara

if __name__ == "__main__":
    main()