import json
import logging
import os
import time
from typing import Dict, Optional, Any, List, Union
import pandas as pd
import requests

# TradingView bot engellerini aşmak için User-Agent Yaması
ORIGINAL_POST = requests.post

def patched_post(*args, **kwargs):
    headers = kwargs.get('headers', {}) or {}
    headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    headers['Accept'] = 'application/json, text/plain, */*'
    headers['Origin'] = 'https://www.tradingview.com'
    headers['Referer'] = 'https://www.tradingview.com/'
    kwargs['headers'] = headers
    return ORIGINAL_POST(*args, **kwargs)

requests.post = patched_post

from tradingview_ta import get_multiple_analysis, Interval, TA_Handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

FINLAB_PATH = "finlab_data.json"

def load_finlab_data(path: str = FINLAB_PATH) -> Dict[str, Dict[str, Any]]:
    """Finlab temel analiz verilerini JSON dosyasından okur."""
    if not os.path.exists(path):
        logger.warning(f"{path} bulunamadı. Temel analiz verileri boş yüklenecektir.")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Finlab verisi okunurken hata oluştu: {e}")
        return {}

def fetch_chunk_analysis(symbols: List[str], interval: str) -> Dict[str, Any]:
    """Sembol grubunu Chrome tarayıcı kimliği ile TradingView'den çeker."""
    formatted_symbols = [f"BIST:{s}" if not s.startswith("BIST:") else s for s in symbols]
    
    for attempt in range(1, 4):
        try:
            results = get_multiple_analysis(
                screener="turkey",
                interval=interval,
                symbols=formatted_symbols
            )
            if results:
                return results
        except Exception as e:
            logger.warning(f"Grup isteği bekleniyor ({attempt}/3)... {e}")
            time.sleep(3.0 * attempt)

    fallback_results = {}
    for sym in symbols:
        try:
            time.sleep(1.0)
            clean_sym = sym.replace("BIST:", "")
            handler = TA_Handler(
                symbol=clean_sym,
                screener="turkey",
                exchange="BIST",
                interval=interval
            )
            analysis = handler.get_analysis()
            fallback_results[f"BIST:{clean_sym}"] = analysis
        except Exception as e:
            logger.warning(f"{sym} tekil veri hatası: {e}")

    return fallback_results

def check_daily_trend(data: Union[pd.DataFrame, Dict[str, Any]]) -> bool:
    """
    Günlük trend kontrolü: Kapanış > EMA_50 > EMA_200
    Hem DataFrame hem de Dict (row) veri türlerini destekler.
    """
    if data is None:
        return False
        
    try:
        if isinstance(data, pd.DataFrame):
            if data.empty:
                return False
            close = data["Daily_Close"].iloc[-1]
            ema50 = data["Daily_EMA_50"].iloc[-1]
            ema200 = data["Daily_EMA_200"].iloc[-1]
        elif isinstance(data, dict):
            close = data.get("Daily_Close")
            ema50 = data.get("Daily_EMA_50")
            ema200 = data.get("Daily_EMA_200")
        else:
            return False

        if close is None or ema50 is None or ema200 is None:
            return False
            
        if pd.isna(close) or pd.isna(ema50) or pd.isna(ema200):
            return False

        return (close > ema50) and (ema50 > ema200)
    except Exception as e:
        logger.error(f"Günlük trend kontrol hatası: {e}")
        return False

def get_indicators_batch(symbols: List[str], finlab_db: Optional[Dict] = None) -> pd.DataFrame:
    """bot.py tarafından çağrılan ana fonksiyon."""
    if finlab_db is None:
        finlab_db = load_finlab_data()

    logger.info(f"Toplu veri çekiliyor ({len(symbols)} sembol)...")

    chunk_size = 10
    symbol_chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]

    analysis_30m_map = {}
    analysis_daily_map = {}

    for idx, chunk in enumerate(symbol_chunks, 1):
        logger.info(f"Paket {idx}/{len(symbol_chunks)} işleniyor ({len(chunk)} hisse)...")
        
        # 30 Dakikalık Veriler
        res_30m = fetch_chunk_analysis(chunk, Interval.INTERVAL_30_MINUTES)
        analysis_30m_map.update(res_30m)
        time.sleep(1.5)

        # Günlük Veriler
        res_daily = fetch_chunk_analysis(chunk, Interval.INTERVAL_1_DAY)
        analysis_daily_map.update(res_daily)
        time.sleep(2.0)

    rows = []
    for sym in symbols:
        key = f"BIST:{sym}" if not sym.startswith("BIST:") else sym
        
        analysis_30m = analysis_30m_map.get(key)
        analysis_daily = analysis_daily_map.get(key)

        if not analysis_30m or not analysis_daily:
            logger.warning(f"{sym} için TradingView verisi alınamadı, atlanıyor.")
            continue

        try:
            ind_30m = analysis_30m.indicators
            ind_daily = analysis_daily.indicators
            summary_30m = analysis_30m.summary

            finlab_info = finlab_db.get(sym, {})
            finlab_score = finlab_info.get("Finlab_Score", 0)
            fundamental_ok = finlab_info.get("Fundamental_OK", False)

            macd_val = ind_30m.get("MACD.macd")
            macd_sig = ind_30m.get("MACD.signal")
            macd_hist = (macd_val - macd_sig) if (macd_val is not None and macd_sig is not None) else 0.0

            row = {
                "Symbol": sym,
                "Close": ind_30m.get("close"),
                "Open": ind_30m.get("open"),
                "High": ind_30m.get("high"),
                "Low": ind_30m.get("low"),
                "Volume": ind_30m.get("volume"),
                "RSI": ind_30m.get("RSI"),
                "ADX": ind_30m.get("ADX"),
                "EMA_50": ind_30m.get("EMA50"),
                "EMA_200": ind_30m.get("EMA200"),
                "MACD_Hist": macd_hist,
                "ATR": ind_30m.get("ATR"),
                "Vol_SMA20": ind_30m.get("SMA20"),
                "TV_Recommendation": summary_30m.get("RECOMMENDATION", "NEUTRAL"),
                "Daily_EMA_50": ind_daily.get("EMA50"),
                "Daily_EMA_200": ind_daily.get("EMA200"),
                "Daily_Close": ind_daily.get("close"),
                "Finlab_Score": finlab_score,
                "Fundamental_OK": fundamental_ok
            }

            row["Daily_Trend_OK"] = check_daily_trend(row)
            rows.append(row)
        except Exception as e:
            logger.error(f"{sym} verisi ayrıştırılırken hata oluştu: {e}")

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)

def load_price_history(symbol: str, interval: str = Interval.INTERVAL_30_MINUTES) -> Optional[pd.DataFrame]:
    df = get_indicators_batch([symbol])
    return df if not df.empty else None