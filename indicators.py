"""
indicators.py
=============
TradingView (`tradingview-ta`) Çoklu İş Parçacıklı (Multithreaded) Canlı Veri ve 8-İndikatörlü Matris Motoru.

İndikatör Matrisi:
1. RSI (14)
2. MACD & Hist (12, 26, 9)
3. EMA 50 & EMA 200
4. ADX (14) (+DI, -DI)
5. Bollinger Bands (20, 2) (BB.upper, BB.lower, BB.middle)
6. Stochastic Oscillator (Stoch.K, Stoch.D)
7. CCI (Commodity Channel Index 20)
8. Ichimoku Kinko Hyo (Conversion / Base Line)
"""

import sys
import io
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

HISTORY_DIR = os.path.join(os.path.dirname(__file__), "data", "price_history")
os.makedirs(HISTORY_DIR, exist_ok=True)


def clean_symbol(symbol: str) -> str:
    """Sembol adından 'BIST:' ve '.IS' eklerini temizler."""
    return symbol.replace("BIST:", "").replace(".IS", "").upper()


def fetch_chunk_analysis(symbols: List[str], interval: str) -> Dict[str, Any]:
    """Sembol grubunu TradingView'den çeker."""
    clean_symbols = [clean_symbol(s) for s in symbols]
    formatted_symbols = [f"BIST:{s}" for s in clean_symbols]
    
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
            logger.warning(f"TradingView paket isteği denemesi ({attempt}/3)... {e}")
            time.sleep(1.5 * attempt)

    # Fallback: Tekil TA_Handler sorgulamaları
    fallback_results = {}
    for sym in clean_symbols:
        try:
            time.sleep(0.3)
            handler = TA_Handler(
                symbol=sym,
                screener="turkey",
                exchange="BIST",
                interval=interval
            )
            analysis = handler.get_analysis()
            fallback_results[f"BIST:{sym}"] = analysis
        except Exception as e:
            logger.warning(f"[{sym}] TradingView tekil veri çekme hatası: {e}")

    return fallback_results


def check_daily_trend(data: Union[pd.DataFrame, Dict[str, Any]]) -> bool:
    """Günlük trend kontrolü: Günlük Kapanış > Daily EMA 50"""
    if data is None:
        return False
        
    try:
        if isinstance(data, pd.DataFrame):
            if data.empty:
                return False
            close = data["Daily_Close"].iloc[-1]
            ema50 = data["Daily_EMA_50"].iloc[-1]
        elif isinstance(data, dict):
            close = data.get("Daily_Close")
            ema50 = data.get("Daily_EMA_50")
        else:
            return False

        if close is None or ema50 is None or pd.isna(close) or pd.isna(ema50):
            return True

        return float(close) > float(ema50)
    except Exception:
        return True


def save_price_snapshot(row: dict):
    """Her taramadaki fiyat anlık görüntüsünü yerel data/price_history/ dosyasına ekler."""
    try:
        sym = clean_symbol(row.get("Symbol", ""))
        if not sym:
            return
        
        file_path = os.path.join(HISTORY_DIR, f"{sym}.csv")
        new_data = {
            "timestamp": [pd.Timestamp.now()],
            "close": [row.get("Close")],
            "open": [row.get("Open")],
            "high": [row.get("High")],
            "low": [row.get("Low")],
            "volume": [row.get("Volume")],
            "rsi": [row.get("RSI")],
            "adx": [row.get("ADX")],
            "macd_hist": [row.get("MACD_Hist")],
            "bb_upper": [row.get("BB_Upper")],
            "bb_lower": [row.get("BB_Lower")],
            "stoch_k": [row.get("Stoch_K")],
            "cci": [row.get("CCI")]
        }
        df_new = pd.DataFrame(new_data)
        
        if os.path.exists(file_path):
            df_existing = pd.read_csv(file_path)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.tail(200).to_csv(file_path, index=False)
        else:
            df_new.to_csv(file_path, index=False)
    except Exception as e:
        logger.warning(f"Yerel fiyat geçmişi kaydetme hatası ({row.get('Symbol')}): {e}")


def load_price_history(symbol: str) -> Optional[pd.DataFrame]:
    """Yerel kaydedilmiş fiyat geçmişini yükler."""
    try:
        clean_sym = clean_symbol(symbol)
        file_path = os.path.join(HISTORY_DIR, f"{clean_sym}.csv")
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                return df
    except Exception as e:
        logger.warning(f"Yerel fiyat geçmişi okuma hatası ({symbol}): {e}")
    return None


def get_indicators_batch(symbols: List[str]) -> pd.DataFrame:
    """
    Tüm BIST hisselerinin 30m intraday ve 1d daily verilerini ThreadPoolExecutor ile paralel çeker.
    """
    clean_syms = [clean_symbol(s) for s in symbols]
    logger.info(f"⚡ TradingView Paralel Veri Çekme Başlatıldı ({len(clean_syms)} Hisse)...")

    chunk_size = 15
    symbol_chunks = [clean_syms[i:i + chunk_size] for i in range(0, len(clean_syms), chunk_size)]

    analysis_30m_map = {}
    analysis_daily_map = {}

    # ThreadPoolExecutor ile Paralel Paket İndirme
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_30m = {executor.submit(fetch_chunk_analysis, chunk, Interval.INTERVAL_30_MINUTES): chunk for chunk in symbol_chunks}
        future_daily = {executor.submit(fetch_chunk_analysis, chunk, Interval.INTERVAL_1_DAY): chunk for chunk in symbol_chunks}

        for future in as_completed(future_30m):
            try:
                res = future.result()
                if res:
                    analysis_30m_map.update(res)
            except Exception as e:
                logger.warning(f"30m paralel paket hatası: {e}")

        for future in as_completed(future_daily):
            try:
                res = future.result()
                if res:
                    analysis_daily_map.update(res)
            except Exception as e:
                logger.warning(f"Günlük paralel paket hatası: {e}")

    rows = []
    for sym in clean_syms:
        key = f"BIST:{sym}"
        
        analysis_30m = analysis_30m_map.get(key)
        analysis_daily = analysis_daily_map.get(key)

        if not analysis_30m or not analysis_daily:
            continue

        try:
            ind_30m = analysis_30m.indicators
            ind_daily = analysis_daily.indicators
            summary_30m = analysis_30m.summary

            close_price = ind_30m.get("close")
            if close_price is None or float(close_price) <= 0:
                continue

            # MACD
            macd_val = ind_30m.get("MACD.macd")
            macd_sig = ind_30m.get("MACD.signal")
            macd_hist = (macd_val - macd_sig) if (macd_val is not None and macd_sig is not None) else 0.0

            # Bollinger Bands
            bb_upper = ind_30m.get("BB.upper", close_price * 1.02)
            bb_lower = ind_30m.get("BB.lower", close_price * 0.98)
            bb_middle = ind_30m.get("SMA20", close_price)

            # Stochastic
            stoch_k = ind_30m.get("Stoch.K", 50.0)
            stoch_d = ind_30m.get("Stoch.D", 50.0)

            # CCI (Commodity Channel Index)
            cci_val = ind_30m.get("CCI20", 0.0)

            # Ichimoku Kinko Hyo
            ichimoku_bline = ind_30m.get("Ichimoku.BLine", close_price)
            ichimoku_cline = ind_30m.get("Ichimoku.CLine", close_price)

            vol_sma20 = ind_30m.get("SMA20") or ind_30m.get("volume")

            row = {
                "Symbol": sym,
                "Close": float(close_price),
                "Open": float(ind_30m.get("open", close_price)),
                "High": float(ind_30m.get("high", close_price)),
                "Low": float(ind_30m.get("low", close_price)),
                "Volume": float(ind_30m.get("volume", 0.0)),
                "RSI": float(ind_30m.get("RSI", 50.0)) if ind_30m.get("RSI") is not None else 50.0,
                "ADX": float(ind_30m.get("ADX", 20.0)) if ind_30m.get("ADX") is not None else 20.0,
                "EMA_50": float(ind_30m.get("EMA50", close_price)) if ind_30m.get("EMA50") is not None else close_price,
                "EMA_200": float(ind_30m.get("EMA200", close_price)) if ind_30m.get("EMA200") is not None else close_price,
                "MACD_Hist": macd_hist,
                "BB_Upper": float(bb_upper) if bb_upper is not None else close_price * 1.02,
                "BB_Lower": float(bb_lower) if bb_lower is not None else close_price * 0.98,
                "BB_Middle": float(bb_middle) if bb_middle is not None else close_price,
                "Stoch_K": float(stoch_k) if stoch_k is not None else 50.0,
                "Stoch_D": float(stoch_d) if stoch_d is not None else 50.0,
                "CCI": float(cci_val) if cci_val is not None else 0.0,
                "Ichimoku_BLine": float(ichimoku_bline) if ichimoku_bline is not None else close_price,
                "Ichimoku_CLine": float(ichimoku_cline) if ichimoku_cline is not None else close_price,
                "ATR": float(ind_30m.get("ATR", close_price * 0.02)) if ind_30m.get("ATR") is not None else close_price * 0.02,
                "Vol_SMA20": float(vol_sma20) if vol_sma20 is not None else None,
                "TV_Recommendation": summary_30m.get("RECOMMENDATION", "NEUTRAL"),
                "Daily_EMA_50": float(ind_daily.get("EMA50", close_price)) if ind_daily.get("EMA50") is not None else close_price,
                "Daily_Close": float(ind_daily.get("close", close_price)) if ind_daily.get("close") is not None else close_price
            }

            row["Daily_Trend_OK"] = check_daily_trend(row)
            save_price_snapshot(row)
            rows.append(row)
        except Exception as e:
            logger.error(f"[{sym}] Veri ayrıştırma hatası: {e}")

    if not rows:
        return pd.DataFrame()

    logger.info(f"✅ Toplam {len(rows)} hissenin 8-indikatörlü teknik matrisi çekildi.")
    return pd.DataFrame(rows)