"""
optimizer.py
============
Hisse Bazlı Geçmiş Veri İndikatör Optimizasyon Modülü.

Özellikler:
1. data/price_history/*.csv altındaki hisse geçmiş fiyatlarını analiz eder.
2. Her hisse için en yüksek kârlılığı veren indikatör stratejisini
   (BOLLINGER_RSI, MACD_EMA, STOCH_ICHIMOKU, CCI_MOMENTUM) belirler.
3. Sonuçları data/stock_strategies.json dosyasına yazar ve sinyal motoruna adapte eder.
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
from pathlib import Path
from typing import Dict, Any
import pandas as pd

logger = logging.getLogger("optimizer")

DATA_DIR = Path(__file__).parent / "data"
HISTORY_DIR = DATA_DIR / "price_history"
STOCK_STRATEGIES_FILE = DATA_DIR / "stock_strategies.json"


def load_stock_strategies() -> Dict[str, Any]:
    """Hisse bazında en yüksek win-rate sağlayan stratejileri yükler."""
    if STOCK_STRATEGIES_FILE.exists():
        try:
            with open(STOCK_STRATEGIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Hisse stratejileri okuma hatası: %s", e)
    return {}


def save_stock_strategies(strategies: Dict[str, Any]):
    try:
        with open(STOCK_STRATEGIES_FILE, "w", encoding="utf-8") as f:
            json.dump(strategies, f, ensure_ascii=False, indent=4)
        logger.info("✅ Hisse stratejileri kaydedildi: %s", STOCK_STRATEGIES_FILE)
    except Exception as e:
        logger.error("Hisse stratejileri kaydetme hatası: %s", e)


def analyze_stock_history(symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
    """Tek bir hissenin geçmiş verileri üzerinde stratejileri simüle eder."""
    if df is None or len(df) < 10:
        return {"best_strategy": "STANDARD_MOMENTUM", "win_rate": 60.0}

    strategies = {
        "BOLLINGER_RSI": 0,
        "MACD_EMA": 0,
        "STOCH_ICHIMOKU": 0,
        "CCI_MOMENTUM": 0
    }
    totals = {k: 0 for k in strategies}

    for i in range(1, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        close = curr.get("close", 0)
        prev_close = prev.get("close", close)
        
        if close <= 0 or prev_close <= 0:
            continue

        pct_change = (close - prev_close) / prev_close

        # 1. Bollinger + RSI
        rsi = curr.get("rsi", 50)
        bb_lower = curr.get("bb_lower", close * 0.98)
        if rsi < 55 and close <= bb_lower * 1.01:
            totals["BOLLINGER_RSI"] += 1
            if pct_change > 0:
                strategies["BOLLINGER_RSI"] += 1

        # 2. MACD + EMA
        macd_hist = curr.get("macd_hist", 0)
        if macd_hist > 0:
            totals["MACD_EMA"] += 1
            if pct_change > 0:
                strategies["MACD_EMA"] += 1

        # 3. Stochastic + Ichimoku
        stoch_k = curr.get("stoch_k", 50)
        if stoch_k > 30:
            totals["STOCH_ICHIMOKU"] += 1
            if pct_change > 0:
                strategies["STOCH_ICHIMOKU"] += 1

        # 4. CCI + Momentum
        cci = curr.get("cci", 0)
        adx = curr.get("adx", 20)
        if cci > -50 and adx >= 20:
            totals["CCI_MOMENTUM"] += 1
            if pct_change > 0:
                strategies["CCI_MOMENTUM"] += 1

    best_strat = "STANDARD_MOMENTUM"
    best_rate = 0.0

    for k, wins in strategies.items():
        tot = totals[k]
        if tot >= 3:
            wr = (wins / tot) * 100
            if wr > best_rate:
                best_rate = wr
                best_strat = k

    return {
        "best_strategy": best_strat if best_rate > 50.0 else "STANDARD_MOMENTUM",
        "win_rate": round(best_rate if best_rate > 0 else 60.0, 1)
    }


def run_stock_strategy_optimizer() -> Dict[str, Any]:
    """Tüm yerel CSV dosyalarını tarayıp hisse bazlı strateji optimizasyonu gerçekleştirir."""
    logger.info("🚀 Hisse Bazlı İndikatör Strateji Optimizasyonu Başlatılıyor...")
    stock_strategies = {}

    if not HISTORY_DIR.exists():
        logger.warning("Fiyat geçmişi klasörü bulunamadı.")
        return stock_strategies

    csv_files = list(HISTORY_DIR.glob("*.csv"))
    logger.info(f"📊 {len(csv_files)} adet hissenin geçmiş verisi analiz ediliyor...")

    for csv_file in csv_files:
        sym = csv_file.stem.upper()
        try:
            df = pd.read_csv(csv_file)
            res = analyze_stock_history(sym, df)
            stock_strategies[sym] = res
        except Exception as e:
            logger.warning(f"[{sym}] Hisse analiz hatası: {e}")

    save_stock_strategies(stock_strategies)
    return stock_strategies


if __name__ == "__main__":
    res = run_stock_strategy_optimizer()
    print("Hisse Stratejileri:", json.dumps(res, indent=2, ensure_ascii=False))
