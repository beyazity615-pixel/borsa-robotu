import requests
import pandas as pd
import time
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Genişletilmiş BIST 100 Hisse Listesi
BIST100_TICKERS = [
    "AEFES", "AGHOL", "AHGAZ", "AKBNK", "AKCNS", "AKFGY", "AKSA", "AKSEN",
    "ALARK", "ALBRK", "ALFAS", "ANSGR", "ARCLK", "ASELS", "ASTOR", "BERA",
    "BIMAS", "BRSAN", "BRYAT", "BUCIM", "CANTE", "CCOLA", "CIMSA", "CWENE",
    "DOAS", "DOHOL", "ECILC", "EGEEN", "EKGYO", "ENJSA", "ENKAI", "EREGL",
    "EUPWR", "EUREK", "FROTO", "GARAN", "GESAN", "GUBRF", "HALKB", "HEKTS",
    "ISCTR", "ISGYO", "ISMEN", "KCAER", "KCHOL", "KONTR", "KORDS", "KOZAL",
    "KOZAA", "KRDMD", "MAVI", "MGROS", "MIATK", "ODAS", "OTKAR", "OYAKC",
    "PETKM", "PGSUS", "QUAGR", "SAHOL", "SASA", "SAYAS", "SDTTR", "SISE",
    "SKBNK", "SOKM", "TABGD", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO",
    "TSKB", "TTKOM", "TTRAK", "TUPRS", "TURSG", "ULKER", "VAKBN", "VESBE",
    "VESTL", "YEOTK", "YKBNK", "YYLGD", "ZOREN"
]

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[LOG]: {message}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_bist_data(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.IS?interval=1d&range=1y"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            result = resp.json().get("chart", {}).get("result", [])
            if result:
                closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
                closes = [c for c in closes if c is not None]
                if len(closes) >= 50:
                    return pd.DataFrame({"close": closes})
    except Exception:
        pass
    return None

def check_stock_signal(ticker):
    df = get_bist_data(ticker)
    if df is None:
        return None

    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    last_price = df['close'].iloc[-1]
    last_ema50 = df['EMA50'].iloc[-1]
    last_rsi = df['RSI'].iloc[-1]

    # Strateji Koşulu
    if (last_price > last_ema50) and (48 <= last_rsi <= 72):
        # En yüksek net getirili optimizasyon parametreleri (%4.0 Kâr Al / %2.5 Stop)
        tp_price = last_price * 1.040
        sl_price = last_price * 0.975

        return (
            f"🎯 **CANLI BIST AL SİNYALİ**: #{ticker}\n"
            f"------------------------------------\n"
            f"💵 **Güncel Fiyat:** {last_price:.2f} TRY\n"
            f"🎯 **Kâr Al Target (%4.0):** {tp_price:.2f} TRY\n"
            f"🛑 **Stop Loss (%2.5):** {sl_price:.2f} TRY\n"
            f"📊 **RSI:** {last_rsi:.1f} | **EMA50:** {last_ema50:.2f}"
        )
    return None

def main():
    print(f"🚀 BIST 100 Canlı Sinyal Botu Başlatıldı ({len(BIST100_TICKERS)} Hisse Taranıyor)...")
    send_telegram(f"🤖 **BIST 100 Canlı Sinyal Botu Başlatıldı!**\n📊 Toplam {len(BIST100_TICKERS)} hisse taranıyor. (%4.0 TP / %2.5 SL)")

    while True:
        print("\n[BIST 100 Taranıyor...]")
        signal_count = 0
        for ticker in BIST100_TICKERS:
            msg = check_stock_signal(ticker)
            if msg:
                send_telegram(msg)
                signal_count += 1
                print(f"Sinyal Gönderildi: {ticker}")
            time.sleep(0.5)

        print(f"Tarama tamamlandı. {signal_count} adet sinyal bulundu. 1 saat bekleniyor...")
        time.sleep(3600)

if __name__ == "__main__":
    main()