import os
import time
import threading
import requests
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from flask import Flask, render_template_string

# .env dosyasından değişkenleri yükle
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 1. RENDER İÇİN FLASK SUNUCUSU VE ARAYÜZ ---
app = Flask(__name__)

# Modern HTML + CSS Tasarımı (Tek dosya içinde entegre)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Borsa Robotu - Canlı Takip Paneli</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', sans-serif; }
        body { background-color: #f4f7f6; color: #333; padding: 30px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; background: #ffffff; padding: 25px 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 30px; }
        .logo-area h1 { font-size: 24px; color: #1a1a1a; }
        .logo-area p { font-size: 14px; color: #666; margin-top: 5px; }
        .status-badge { display: flex; align-items: center; gap: 8px; background: #e6f4ea; color: #137333; padding: 8px 16px; border-radius: 20px; font-weight: 500; font-size: 14px; }
        .dot { width: 8px; height: 8px; background-color: #137333; border-radius: 50%; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.3); opacity: 0.5; } 100% { transform: scale(1); opacity: 1; } }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background: #ffffff; padding: 20px 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .card h3 { font-size: 14px; color: #666; font-weight: 500; }
        .metric-value { font-size: 28px; font-weight: 700; margin: 10px 0 5px 0; }
        .metric-value.positive { color: #137333; }
        .metric-value.neutral { color: #1a73e8; }
        .sub-text { font-size: 12px; color: #888; }
        .section-card { background: #ffffff; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .section-card h2 { font-size: 18px; margin-bottom: 20px; color: #222; }
        .table-responsive { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th, td { padding: 12px 15px; border-bottom: 1px solid #eee; font-size: 14px; }
        th { background-color: #fafafa; color: #555; font-weight: 600; }
        .positive { color: #137333; font-weight: 600; }
        .badge { padding: 5px 10px; border-radius: 6px; font-size: 12px; font-weight: 500; }
        .badge.info { background: #e8f0fe; color: #1967d2; }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo-area">
                <h1>📈 Borsa Robotu Takip Paneli</h1>
                <p>Canlı Sinyaller ve Portföy Durumu</p>
            </div>
            <div class="status-badge">
                <span class="dot"></span> Borsa Botu 7/24 Canlı ve Aktif!
            </div>
        </header>

        <div class="metrics-grid">
            <div class="card">
                <h3>Tahmini Başarı / Portföy Durumu</h3>
                <p class="metric-value positive">Aktif</p>
                <span class="sub-text">Render & Cron-Job Senkronize</span>
            </div>
            <div class="card">
                <h3>Taranan Sembol</h3>
                <p class="metric-value neutral">44 Adet</p>
                <span class="sub-text">BIST 100 Seçmeleri</span>
            </div>
        </div>

        <div class="section-card">
            <h2>⏳ Bot Durumu ve Ping Bilgisi</h2>
            <p>Sunucu sağlıklı bir şekilde çalışıyor. Cron-job her 10 dakikada bir bu sayfaya ping atarak botun uyumasını önlemektedir.</p>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

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
             
            last_close = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2])
            change_pct = ((last_close - prev_close) / prev_close) * 100
             
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