import requests
import pandas as pd

BIST100_TICKERS = [
    "AKBNK", "ARCLK", "ASELS", "BIMAS", "EREGL", "FROTO", "GARAN", "HEKTS", 
    "KCHOL", "KONTR", "KOZAL", "KRDMD", "PETKM", "PGSUS", "SAHOL", "SASA", 
    "SISE", "TCELL", "THYAO", "TUPRS", "YKBNK"
]

def get_bist_history(ticker):
    """Yahoo Finance doğrudan API'sinden 1 yıllık günlük kapanış verisini çeker."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.IS?interval=1d&range=1y"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
                # None değerleri temizle
                closes = [c for c in closes if c is not None]
                if len(closes) >= 100:
                    return pd.DataFrame({"close": closes})
    except Exception:
        pass
    return None

def run_backtest_on_stock(ticker, take_profit=0.05, stop_loss=0.03):
    df = get_bist_history(ticker)
    if df is None or len(df) < 50:
        return []

    # İndikatörler (EMA50 ve RSI)
    df['EMA50'] = df['close'].ewm(span=min(50, len(df)-1), adjust=False).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    trades = []
    in_trade = False
    entry_price = 0

    # Veri uzunluğuna göre başlangıç indeksi
    start_idx = 50 if len(df) > 50 else 15

    for i in range(start_idx, len(df)):
        price = df['close'].iloc[i]
        ema50 = df['EMA50'].iloc[i]
        rsi = df['RSI'].iloc[i]

        # AL Sinyali Koşulu: Fiyat > EMA50 ve RSI 48-72 arası
        signal = (price > ema50) and (48 <= rsi <= 72)

        if not in_trade and signal:
            in_trade = True
            entry_price = price
        elif in_trade:
            pct_change = (price - entry_price) / entry_price

            if pct_change >= take_profit:
                trades.append({'Ticker': ticker, 'Result': 'WIN', 'Return': pct_change})
                in_trade = False
            elif pct_change <= -stop_loss:
                trades.append({'Ticker': ticker, 'Result': 'LOSS', 'Return': pct_change})
                in_trade = False

    return trades

def run_full_backtest():
    print("🚀 BIST 100 Geçmiş Verileriyle Backtest Hesaplanıyor (%5 Kâr Al / %3 Stop Loss)...\n")
    all_trades = []

    for ticker in BIST100_TICKERS:
        trades = run_backtest_on_stock(ticker)
        all_trades.extend(trades)

    if not all_trades:
        print("❌ Seçilen parametrelerde işlem bulunamadı.")
        return

    df_res = pd.DataFrame(all_trades)
    total_trades = len(df_res)
    wins = len(df_res[df_res['Result'] == 'WIN'])
    losses = len(df_res[df_res['Result'] == 'LOSS'])
    win_rate = (wins / total_trades) * 100
    total_return = df_res['Return'].sum() * 100

    print("================ BACKTEST PERFORMANS RAPORU ================")
    print(f"Taranan Hisse Sayısı     : {len(BIST100_TICKERS)}")
    print(f"Geçmiş Üretilen İşlem   : {total_trades}")
    print(f"Kârlı Kapanan (WIN)      : {wins}")
    print(f"Zararla Kapanan (LOSS)  : {losses}")
    print(f"🎯 BAŞARI ORANI (Win Rate) : %{win_rate:.2f}")
    print(f"📈 Kumulatif Net Getiri   : %{total_return:.2f}")
    print("============================================================\n")

if __name__ == "__main__":
    run_full_backtest()