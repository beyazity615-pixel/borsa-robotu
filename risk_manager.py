"""
risk_manager.py
===============
Dinamik ATR Tabanlı Risk Yönetimi ve Sektörel Korelasyon Filtreleme Modülü.

Özellikler:
1. Dinamik Kar Al (TP) ve Stop-Loss (SL): Piyasa oynaklığına (ATR) duyarlı esnek marj hesaplama.
2. Sektörel Korelasyon & Risk Dağıtımı: Aynı sektörden aynı anda sinyal üreten hisseler arasında
   en yüksek teknik puana sahip olanı seçip diğerlerini eleyerek sektör riski birikimini önleme.
"""

import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple
from bist_symbols import get_sector

logger = logging.getLogger("risk_manager")


def calculate_dynamic_levels(close_price: float, atr_value: float | None = None) -> Tuple[float, float, float, float]:
    """
    Hissenin anlık ATR (Average True Range) değerine göre dinamik TP ve SL seviyelerini hesaplar.
    
    Dönüş: (tp_price, sl_price, tp_pct, sl_pct)
    """
    if close_price <= 0:
        return 0.0, 0.0, 0.0, 0.0

    if atr_value is None or pd.isna(atr_value) or atr_value <= 0:
        atr_value = close_price * 0.02

    # ATR Çarpanları: Kar Al (TP) 1.8x ATR (min %2.5), Stop Loss (SL) 1.2x ATR (min %1.5)
    tp_margin = max(atr_value * 1.8, close_price * 0.025)
    sl_margin = max(atr_value * 1.2, close_price * 0.015)

    tp_price = close_price + tp_margin
    sl_price = close_price - sl_margin

    tp_pct = (tp_margin / close_price) * 100
    sl_pct = (sl_margin / close_price) * 100

    return round(tp_price, 2), round(sl_price, 2), round(tp_pct, 2), round(sl_pct, 2)


def calculate_signal_score(row: Dict[str, Any]) -> float:
    """Sinyal üreten hisse için karşılaştırma ve sıralama skoru hesaplar."""
    score = 0.0
    
    # 1. TradingView Tavsiye Puanı
    tv_rec = row.get("TV_Recommendation", "NEUTRAL")
    if tv_rec == "STRONG_BUY":
        score += 30.0
    elif tv_rec == "BUY":
        score += 15.0

    # 2. ADX Trend Gücü
    adx = row.get("ADX")
    if adx and not pd.isna(adx):
        score += float(adx)

    # 3. RSI Optimal Bölge (52 - 65)
    rsi = row.get("RSI")
    if rsi and not pd.isna(rsi):
        if 52 <= rsi <= 65:
            score += 15.0
        elif 48 <= rsi <= 72:
            score += 5.0

    # 4. MACD Momentum
    macd_hist = row.get("MACD_Hist")
    if macd_hist and not pd.isna(macd_hist) and macd_hist > 0:
        score += 10.0

    return score


def filter_sector_concentration(candidates: List[Dict[str, Any]], max_per_sector: int = 1) -> List[Dict[str, Any]]:
    """
    Aynı sektörden sinyal veren hisseler arasında skor derecelendirmesi yaparak
    sektör bazında maksimum sınırın üzerindeki daha düşük skorlu hisseleri eler.
    """
    if not candidates:
        return []

    # Sektörlere göre grupla
    sector_groups: Dict[str, List[Dict[str, Any]]] = {}
    for cand in candidates:
        sym = cand.get("Symbol", "")
        sector = get_sector(sym)
        cand["_sector"] = sector
        cand["_score"] = calculate_signal_score(cand)
        
        if sector not in sector_groups:
            sector_groups[sector] = []
        sector_groups[sector].append(cand)

    filtered_signals: List[Dict[str, Any]] = []

    for sector, group in sector_groups.items():
        # Skora göre büyükten küçüğe sırala
        sorted_group = sorted(group, key=lambda x: x.get("_score", 0.0), reverse=True)
        selected = sorted_group[:max_per_sector]
        filtered_signals.extend(selected)

        if len(group) > max_per_sector:
            rejected_syms = [x.get("Symbol") for x in sorted_group[max_per_sector:]]
            logger.info(f"🛡️ Sektörel Korelasyon Filtresi [{sector}]: {selected[0]['Symbol']} seçildi ({selected[0]['_score']:.1f} puan), daha düşük skorlu {rejected_syms} elendi.")

    return filtered_signals


if __name__ == "__main__":
    test_close = 100.0
    test_atr = 2.5
    tp, sl, tp_p, sl_p = calculate_dynamic_levels(test_close, test_atr)
    print(f"Test Fiyat: {test_close} TL | ATR: {test_atr}")
    print(f"Hesaplanan TP: {tp} TL (+%{tp_p:.2f}) | SL: {sl} TL (-%{sl_p:.2f})")
