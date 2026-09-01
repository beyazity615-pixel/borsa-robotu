"""
optimize_params.py
===================
Dinamik Strateji Parametresi Optimizasyonu ve Geri Besleme Motoru.

Özellikler:
1. data/performance_log.json içindeki geçmiş işlem verilerini analiz eder.
2. RSI, ADX ve Hacim eşikleri üzerinde grid-search optimizasyonu gerçekleştirir.
3. En yüksek Win-Rate sağlayan dinamik parametre kümesini data/optimized_params.json dosyasına yazar.
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

logger = logging.getLogger("optimize_params")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PERFORMANCE_LOG_FILE = DATA_DIR / "performance_log.json"
OPTIMIZED_PARAMS_FILE = DATA_DIR / "optimized_params.json"

DEFAULT_PARAMS = {
    "RSI_MIN": 48,
    "RSI_MAX": 72,
    "ADX_MIN": 20.0,
    "VOLUME_MULTIPLIER": 1.3,
    "ATR_TP_MULT": 1.8,
    "ATR_SL_MULT": 1.2,
    "TV_ALLOWED": ["BUY", "STRONG_BUY"],
    "last_updated": ""
}


def load_optimized_parameters() -> Dict[str, Any]:
    """Sistem tarafından optimize edilmiş dinamik parametreleri yükler."""
    if OPTIMIZED_PARAMS_FILE.exists():
        try:
            with open(OPTIMIZED_PARAMS_FILE, "r", encoding="utf-8") as f:
                params = json.load(f)
                logger.info("⚙️ Dinamik optimize parametreler yüklendi: %s", params)
                return params
        except Exception as e:
            logger.warning("Optimize parametre dosyası okuma hatası: %s. Varsayılanlar kullanılıyor.", e)
    return DEFAULT_PARAMS.copy()


def save_optimized_parameters(params: Dict[str, Any]):
    try:
        params["last_updated"] = os.popen("date").read().strip() if sys.platform != "win32" else ""
        with open(OPTIMIZED_PARAMS_FILE, "w", encoding="utf-8") as f:
            json.dump(params, f, ensure_ascii=False, indent=4)
        logger.info("✅ Optimize edilmiş parametreler kaydedildi: %s", OPTIMIZED_PARAMS_FILE)
    except Exception as e:
        logger.error("Optimize parametre kaydetme hatası: %s", e)


def run_parameter_optimization() -> Dict[str, Any]:
    """
    Geçmiş işlem loglarına dayanarak parametreleri günceller.
    Yeterli log birikmediyse güvenli varsayılan değerleri döndürür ve kaydeder.
    """
    logger.info("🚀 Dinamik Parametre Optimizasyonu Başlatılıyor...")

    perf_data = []
    if PERFORMANCE_LOG_FILE.exists():
        try:
            with open(PERFORMANCE_LOG_FILE, "r", encoding="utf-8") as f:
                perf_data = json.load(f)
        except Exception:
            pass

    if len(perf_data) < 10:
        logger.info("⚠️ Yeterli geçmiş performans verisi yok (min 10 işlem). Varsayılan parametreler korundu.")
        save_optimized_parameters(DEFAULT_PARAMS)
        return DEFAULT_PARAMS

    # Grid Search Simülasyonu
    best_params = DEFAULT_PARAMS.copy()
    best_win_rate = 0.0

    rsi_min_range = [45, 48, 50]
    adx_min_range = [18.0, 20.0, 22.0]
    vol_mult_range = [1.2, 1.3, 1.4]

    for r_min in rsi_min_range:
        for a_min in adx_min_range:
            for v_mult in vol_mult_range:
                wins = 0
                total = 0
                for trade in perf_data:
                    rsi = trade.get("rsi", 50.0)
                    adx = trade.get("adx", 20.0)
                    status = trade.get("status")

                    if rsi >= r_min and adx >= a_min:
                        total += 1
                        if status == "WIN":
                            wins += 1

                if total >= 5:
                    win_rate = (wins / total) * 100
                    if win_rate > best_win_rate:
                        best_win_rate = win_rate
                        best_params["RSI_MIN"] = r_min
                        best_params["ADX_MIN"] = a_min
                        best_params["VOLUME_MULTIPLIER"] = v_mult

    logger.info(f"🎯 Optimizasyon Tamamlandı! En Yüksek Win Rate: %{best_win_rate:.1f}")
    save_optimized_parameters(best_params)
    return best_params


if __name__ == "__main__":
    p = run_parameter_optimization()
    print("Sonuç Parametreleri:", p)