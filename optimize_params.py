import requests
import pandas as pd

BIST100_TICKERS = [
    "AKBNK", "ARCLK", "ASELS", "BIMAS", "EREGL", "FROTO", "GARAN", "HEKTS", 
    "KCHOL", "KONTR", "KOZAL", "KRDMD", "PETKM", "PGSUS", "SAHOL", "SASA", 
    "SISE", "TCELL", "THYAO", "TUPRS", "YKBNK"
]

def get_bist_history(ticker):
    """Yahoo Finance API'sinden 1 yıllık verileri çeker."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.IS?interval=1d&range=1y"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            result = resp.json().get("chart", {}).get("result", [])
            if result:
                closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
                closes = [c for c in closes if c is not None]
                if len(closes) >= 100:
                    return pd.DataFrame({"close": closes})
    except Exception:
        pass
    return None

def run_backtest_with_params(stock_data, take_profit, stop_loss):
    all_trades = []
    
    for ticker, df in stock_data.items():
        if df is None or len(df) < 50:
            continue

        df_copy = df.copy()
        df_copy['EMA50'] = df_copy['close'].ewm(span=50, adjust=False).mean()
        
        delta = df_copy['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_copy['RSI'] = 100 - (100 / (1 + rs))

        in_trade = False
        entry_price = 0

        for i in range(50, len(df_copy)):
            price = df_copy['close'].iloc[i]
            ema50 = df_copy['EMA50'].iloc[i]
            rsi = df_copy['RSI'].iloc[i]

            signal = (price > ema50) and (48 <= rsi <= 72)

            if not in_trade and signal:
                in_trade = True
                entry_price = price
            elif in_trade:
                pct_change = (price - entry_price) / entry_price

                if pct_change >= take_profit:
                    all_trades.append({'Result': 'WIN', 'Return': pct_change})
                    in_trade = False
                elif pct_change <= -stop_loss:
                    all_trades.append({'Result': 'LOSS', 'Return': pct_change})
                    in_trade = False

    if not all_trades:
        return None

    df_res = pd.DataFrame(all_trades)
    total_trades = len(df_res)
    wins = len(df_res[df_res['Result'] == 'WIN'])
    win_rate = (wins / total_trades) * 100
    total_return = df_res['Return'].sum() * 100

    return {
        "TP (%)": f"%{take_profit*100:.1f}",
        "SL (%)": f"%{stop_loss*100:.1f}",
        "Toplam İşlem": total_trades,
        "Win Rate": win_rate,
        "Net Getiri (%)": total_return
    }

def run_grid_search():
    print("⏳ Hisselerin geçmiş verileri indiriliyor...\n")
    stock_data = {}
    for ticker in BIST100_TICKERS:
        stock_data[ticker] = get_bist_history(ticker)

    print("🚀 Parametre Optimizasyonu Başlatılıyor (Farklı TP/SL Kombinasyonları Test Ediliyor)...\n")
    
    # Test edilecek TP ve SL değerleri
    tp_range = [0.02, 0.03, 0.04, 0.05, 0.06]  # %2, %3, %4, %5, %6
    sl_range = [0.015, 0.02, 0.025, 0.03, 0.04] # %1.5, %2, %2.5, %3, %4

    results = []
    for tp in tp_range:
        for sl in sl_range:
            res = run_backtest_with_params(stock_data, tp, sl)
            if res:
                results.append(res)

    df_results = pd.DataFrame(results)
    
    # Win Rate'e göre sırala
    df_sorted = df_results.sort_values(by="Win Rate", ascending=False)

    print("================ OPTİMİZASYON SONUÇLARI (En Yüksek Win Rate) ================")
    print(df_sorted.to_string(index=False))
    print("==============================================================================\n")

if __name__ == "__main__":
    run_grid_search()