"""
ai_portfolio_manager.py
------------------------
5 farklı AI yatırım personası, BIST teknik (ADX/RSI/EMA/MACD/ATR) ve Finlab
temel verilerini değerlendirerek haftalık, yüzde ağırlıklı, sektör bazında
çeşitlendirilmiş bir konsensüs portföy üretir. Cuma 12:30'da Telegram'a
gönderilir; bot her gün çalıştığında önceki haftalık portföyle karşılaştırma
yapılıp değişiklikler bildirilir.

Not — çoklu-LLM mimarisi: Üçüncü parti sağlayıcılara (OpenAI, Gemini vb.)
bağımlılık varsayılmaz. Her persona kural-tabanlı, deterministik bir skor
motoruyla her zaman çalışır; ANTHROPIC_API_KEY tanımlıysa ek olarak Claude'a
persona sistem promptuyla sorgu yapılıp nitel gerekçe zenginleştirilir.
`_call_llm_persona()` başka sağlayıcı SDK'ları eklemek için izole edilmiştir.

Not — ağırlıklandırma: tradingview-ta geçmiş getiri serisi sağlamadığından
kovaryans tabanlı Markowitz/Sharpe optimizasyonu bu veri kaynağıyla mümkün
değildir. Bunun yerine kompozit skora orantılı, hisse başına ve sektör
başına ağırlık tavanlı bir dağıtım kullanılır (Sharpe optimizasyonuna proxy).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from indicators import get_indicators_batch, load_finlab_data, check_daily_trend
from bist_symbols import DEFAULT_WATCHLIST, get_sector
import telegram_notifier

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("ai_portfolio_manager")

BASE_DIR = Path(__file__).parent
WEEKLY_PORTFOLIO_PATH = BASE_DIR / "data" / "weekly_portfolio.json"
WEEKLY_PORTFOLIO_PATH.parent.mkdir(parents=True, exist_ok=True)

MAX_WEIGHT_PER_STOCK = float(os.environ.get("MAX_WEIGHT_PER_STOCK", "0.25"))
MAX_WEIGHT_PER_SECTOR = float(os.environ.get("MAX_WEIGHT_PER_SECTOR", "0.40"))
MIN_WEIGHT_TO_KEEP = float(os.environ.get("MIN_WEIGHT_TO_KEEP", "0.03"))
TOP_N_PER_PERSONA = int(os.environ.get("TOP_N_PER_PERSONA", "8"))

USE_LLM = os.environ.get("USE_LLM_PERSONAS", "true").lower() == "true"
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


@dataclass
class Persona:
    id: str
    name: str
    archetype: str
    description: str  # LLM sistem promptu olarak da kullanılır
    weights: dict[str, float] = field(default_factory=dict)


PERSONAS: list[Persona] = [
    Persona(
        id="aggressive_momentum",
        name="Agresif Momentum Uzmanı",
        archetype="Aggressive Momentum Trader",
        description=(
            "Kısa vadeli momentum odaklı BIST teknik analisti. ADX ile trend "
            "gücünü, RSI ile ivmeyi, MACD histogramıyla momentum yönünü ve "
            "TradingView tavsiyesini önceliklendirir; zayıf teknik yapılı "
            "hisselerden kaçınır."
        ),
        weights={"adx": 0.30, "rsi": 0.20, "macd": 0.20, "tv_rec": 0.20, "finlab": 0.10},
    ),
    Persona(
        id="conservative_value",
        name="Muhafazakâr Değer Yatırımcısı",
        archetype="Conservative Value Investor",
        description=(
            "Sabırlı, temel analiz odaklı değer yatırımcısı. Finlab_Score ve "
            "Fundamental_OK durumunu önceliklendirir; teknik göstergeleri "
            "yalnızca giriş zamanlaması için ikincil teyit aracı sayar."
        ),
        weights={"finlab": 0.55, "tv_rec": 0.15, "adx": 0.10, "rsi": 0.10, "macd": 0.10},
    ),
    Persona(
        id="quant_risk_parity",
        name="Kantitatif Risk Paritesi",
        archetype="Quantitative Risk Parity",
        description=(
            "Riskten kaçınan kantitatif analist. ATR/Close ile normalize "
            "edilmiş oynaklığı minimize etmeyi hedefler; yüksek oynaklıklı "
            "hisselere düşük, trendi bozulmamış düşük oynaklıklı hisselere "
            "yüksek ağırlık verir."
        ),
        weights={"low_volatility": 0.40, "finlab": 0.20, "adx": 0.20, "tv_rec": 0.20},
    ),
    Persona(
        id="trend_following",
        name="Trend Takip Uzmanı",
        archetype="Trend Following Specialist",
        description=(
            "Uzun vadeli trend takip yatırımcısı. Günlük EMA_50/EMA_200 "
            "altın kesişim yapısını ve fiyatın bu ortalamalara göre "
            "konumunu esas alır; kısa vadeli gürültüye düşük ağırlık verir."
        ),
        weights={"trend": 0.45, "adx": 0.20, "finlab": 0.20, "tv_rec": 0.15},
    ),
    Persona(
        id="multi_factor_balanced",
        name="Çok Faktörlü Dengeli Portföy Yöneticisi",
        archetype="Multi-Factor Balanced Portfolio Manager",
        description=(
            "Deneyimli portföy yöneticisi. Teknik ve temel verileri bütünsel "
            "değerlendirip diğer dört uzmanın (momentum, değer, risk "
            "paritesi, trend takibi) bakış açılarını tartarak dengeli, "
            "maksimum Sharpe oranını hedefleyen, sektör bazında "
            "çeşitlendirilmiş bir portföy önerir. Her öneri için kısa, "
            "somut bir gerekçe yazar."
        ),
        weights={"finlab": 0.25, "tv_rec": 0.25, "adx": 0.15, "rsi": 0.15, "trend": 0.20},
    ),
]


def _norm(value: Optional[float], lo: float, hi: float) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo))) if hi != lo else 0.0


def _tv_rec_score(rec: Optional[str]) -> float:
    mapping = {"STRONG_BUY": 1.0, "BUY": 0.75, "NEUTRAL": 0.4, "SELL": 0.1, "STRONG_SELL": 0.0}
    return mapping.get(rec, 0.3)


def _passes_base_filter(row: dict) -> bool:
    """Ana bot filtresiyle tutarlı asgari uygunluk şartı (bkz. bot.py check_market)."""
    tv_ok = row.get("TV_Recommendation") in ("BUY", "STRONG_BUY", "NEUTRAL")
    finlab_ok = (row.get("Finlab_Score") or 0) >= 40 and row.get("Fundamental_OK") is True
    return tv_ok and finlab_ok


def score_row_for_persona(row: dict, persona: Persona) -> float:
    """0-1 arası kompozit persona skoru."""
    components = {
        "adx": _norm(row.get("ADX"), 15, 45),
        "rsi": _norm(row.get("RSI"), 48, 72),
        "macd": 1.0 if (row.get("MACD_Hist") or 0) > 0 else 0.0,
        "tv_rec": _tv_rec_score(row.get("TV_Recommendation")),
        "finlab": _norm(row.get("Finlab_Score"), 40, 90),
        "trend": 1.0 if check_daily_trend(row) else 0.2,
        "low_volatility": 1.0 - _norm(
            (row.get("ATR") / row["Close"]) if row.get("ATR") and row.get("Close") else None,
            0.005, 0.06,
        ),
    }
    return round(sum(w * components.get(k, 0.0) for k, w in persona.weights.items()), 4)


def _call_llm_persona(persona: Persona, candidates_df: pd.DataFrame) -> Optional[str]:
    """ANTHROPIC_API_KEY tanımlıysa Claude'dan nitel gerekçe üretir; yoksa None döner."""
    if not USE_LLM or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("`anthropic` paketi kurulu değil; LLM sentezi atlanıyor.")
        return None

    data_summary = candidates_df[[
        "Symbol", "RSI", "ADX", "EMA_50", "EMA_200", "MACD_Hist", "ATR",
        "TV_Recommendation", "Finlab_Score",
    ]].round(2).to_string(index=False)

    prompt = (
        f"Güncel BIST teknik/temel veri özeti:\n\n{data_summary}\n\n"
        "Borsa İstanbul'da mevcut teknik trendleri (ADX, RSI, EMA_50, EMA_200, "
        "MACD_Hist, ATR), TradingView tavsiyelerini ve Finlab temel skorlarını "
        "göz önünde bulundurarak, önümüzdeki hafta için maksimum Sharpe "
        "oranına sahip, riski dağıtılmış (sektör/korelasyon dengeli) bir BIST "
        "portföyü oluştur. Her hisse için yüzde ağırlık ve 1-2 cümlelik "
        "gerekçe ver. Yanıtı en fazla 200 kelimede tut."
    )
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=700,
            system=persona.description,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
    except Exception as exc:
        logger.warning("LLM persona çağrısı başarısız (%s): %s", persona.id, exc)
        return None


def _apply_weight_cap(holdings: list[dict], max_weight: float, group_key: Optional[str] = None) -> list[dict]:
    """
    Ağırlık tavanını iteratif uygular; group_key verilirse (ör. 'sector')
    grup toplamına tavan uygular, aksi halde her kaleme ayrı ayrı uygular.

    n eleman × tavan < 1.0 olan (matematiksel olarak imkansız) durumlarda,
    tavan mevcut eleman/grup sayısının izin verdiği asgari eşit-ağırlığın
    altına düşürülmez (aksi halde skor farkı yok sayılıp tüm ağırlıklar
    yapay şekilde eşitlenir).
    """
    if not holdings:
        return holdings

    if group_key is None:
        effective_cap = max(max_weight, 1.0 / len(holdings))
        holdings = sorted(holdings, key=lambda h: h["weight"], reverse=True)
        for _ in range(10):
            over = [h for h in holdings if h["weight"] > effective_cap]
            if not over:
                break
            excess = sum(h["weight"] - effective_cap for h in over)
            for h in over:
                h["weight"] = effective_cap
            under = [h for h in holdings if h["weight"] < effective_cap]
            under_total = sum(h["weight"] for h in under)
            if under_total > 0:
                for h in under:
                    h["weight"] += excess * (h["weight"] / under_total)
        total = sum(h["weight"] for h in holdings)
        if total > 0:
            for h in holdings:
                h["weight"] /= total
        return holdings

    groups = sorted({h[group_key] for h in holdings})
    effective_cap = max(max_weight, 1.0 / len(groups))
    for _ in range(10):
        group_totals = {g: sum(h["weight"] for h in holdings if h[group_key] == g) for g in groups}
        over_groups = {g: t for g, t in group_totals.items() if t > effective_cap}
        if not over_groups:
            break
        for g, total in over_groups.items():
            scale = effective_cap / total
            for h in holdings:
                if h[group_key] == g:
                    h["weight"] *= scale
        excess = sum(t - effective_cap for t in over_groups.values())
        under_group_names = [g for g in groups if g not in over_groups]
        under_total = sum(group_totals[g] for g in under_group_names)
        if under_total > 0:
            for h in holdings:
                if h[group_key] in under_group_names:
                    h["weight"] += excess * (h["weight"] / under_total)
    total = sum(h["weight"] for h in holdings)
    if total > 0:
        for h in holdings:
            h["weight"] /= total
    return holdings


def run_persona(persona: Persona, df: pd.DataFrame, top_n: int = TOP_N_PER_PERSONA) -> dict:
    scored = df.copy()
    scored["score"] = scored.apply(lambda r: score_row_for_persona(r.to_dict(), persona), axis=1)
    scored = scored.sort_values("score", ascending=False).head(top_n)
    scored = scored[scored["score"] > 0]

    if scored.empty:
        return {"persona": persona.name, "archetype": persona.archetype, "holdings": [], "llm_commentary": None}

    total_score = scored["score"].sum()
    holdings = [
        {
            "symbol": r["Symbol"], "weight": r["score"] / total_score, "score": r["score"],
            "sector": get_sector(r["Symbol"]),
            "rsi": r.get("RSI"), "adx": r.get("ADX"),
            "tv_recommendation": r.get("TV_Recommendation"), "finlab_score": r.get("Finlab_Score"),
        }
        for _, r in scored.iterrows()
    ]

    holdings = _apply_weight_cap(holdings, MAX_WEIGHT_PER_STOCK)
    holdings = _apply_weight_cap(holdings, MAX_WEIGHT_PER_SECTOR, group_key="sector")

    return {
        "persona": persona.name, "persona_id": persona.id, "archetype": persona.archetype,
        "holdings": holdings, "llm_commentary": _call_llm_persona(persona, scored),
    }


def build_consensus(persona_results: list[dict], max_weight: float = MAX_WEIGHT_PER_STOCK) -> list[dict]:
    n_personas = len(persona_results)
    agg: dict[str, list[float]] = {}
    meta: dict[str, dict] = {}

    for pr in persona_results:
        for h in pr["holdings"]:
            agg.setdefault(h["symbol"], []).append(h["weight"])
            meta[h["symbol"]] = h

    consensus = [
        {
            "symbol": symbol, "weight": sum(weights) / n_personas, "supporting_personas": len(weights),
            "sector": meta[symbol]["sector"], "rsi": meta[symbol]["rsi"], "adx": meta[symbol]["adx"],
            "tv_recommendation": meta[symbol]["tv_recommendation"], "finlab_score": meta[symbol]["finlab_score"],
        }
        for symbol, weights in agg.items()
    ]
    consensus = [c for c in consensus if c["weight"] >= MIN_WEIGHT_TO_KEEP]
    consensus.sort(key=lambda c: (c["supporting_personas"], c["weight"]), reverse=True)

    consensus = _apply_weight_cap(consensus, max_weight)
    consensus = _apply_weight_cap(consensus, MAX_WEIGHT_PER_SECTOR, group_key="sector")

    total = sum(c["weight"] for c in consensus)
    if total > 0:
        for c in consensus:
            c["weight"] = round(c["weight"] / total, 4)
    return consensus


def build_weekly_portfolio(symbols: Optional[list[str]] = None) -> dict:
    symbols = symbols or DEFAULT_WATCHLIST
    finlab_db = load_finlab_data()

    logger.info("Haftalık AI portföy taraması başladı (%d sembol)...", len(symbols))
    df = get_indicators_batch(symbols, finlab_db)
    if df.empty:
        logger.error("Hiçbir sembol için veri alınamadı; haftalık portföy üretilemedi.")
        return {}

    candidates = df[df.apply(lambda r: _passes_base_filter(r.to_dict()), axis=1)]
    if candidates.empty:
        logger.warning("Temel filtreyi geçen hisse yok; ham veri setiyle devam ediliyor.")
        candidates = df

    persona_results = [run_persona(p, candidates) for p in PERSONAS]
    consensus = build_consensus(persona_results)

    result = {
        "generated_at": datetime.now().isoformat(),
        "week_of": datetime.now().strftime("%Y-W%U"),
        "universe_size": len(symbols),
        "candidates_after_filter": len(candidates),
        "personas": persona_results,
        "consensus_portfolio": consensus,
    }

    WEEKLY_PORTFOLIO_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    logger.info("Haftalık portföy kaydedildi: %s", WEEKLY_PORTFOLIO_PATH)
    return result


def load_last_weekly_portfolio() -> Optional[dict]:
    if not WEEKLY_PORTFOLIO_PATH.exists():
        return None
    try:
        return json.loads(WEEKLY_PORTFOLIO_PATH.read_text())
    except json.JSONDecodeError:
        return None


def format_weekly_telegram_report(result: dict) -> str:
    if not result:
        return "⚠️ Haftalık AI portföy raporu üretilemedi (veri alınamadı)."

    lines = [
        f"🤖 *HAFTALIK AI PORTFÖY RAPORU* — {result['week_of']}",
        f"_Üretim zamanı: {result['generated_at'][:16].replace('T', ' ')}_",
        "",
        "📊 *5 AI Personasının Konsensüs Portföyü:*",
    ]
    for c in result["consensus_portfolio"]:
        lines.append(
            f"• *{c['symbol']}* ({c['sector']}): %{c['weight']*100:.1f}  "
            f"(destek: {c['supporting_personas']}/5 AI, TV: {c['tv_recommendation']}, "
            f"Finlab: {c['finlab_score']})"
        )

    lines.append("")
    lines.append("🧠 *Persona Bazlı Öne Çıkanlar:*")
    for pr in result["personas"]:
        top3 = ", ".join(f"{h['symbol']} (%{h['weight']*100:.0f})" for h in pr["holdings"][:3])
        lines.append(f"— *{pr['persona']}* ({pr.get('archetype', '')}): {top3 or 'uygun hisse bulunamadı'}")
        if pr.get("llm_commentary"):
            snippet = pr["llm_commentary"].strip().replace("\n", " ")[:220]
            lines.append(f"   💬 {snippet}...")

    lines.append("")
    lines.append("_Not: Bu rapor otomatik üretilmiştir, yatırım tavsiyesi değildir._")
    return "\n".join(lines)


def run_friday_job(symbols: Optional[list[str]] = None) -> dict:
    """Cuma 12:30 tetikleyicisi tarafından (veya --weekly-ai ile manuel) çağrılır."""
    result = build_weekly_portfolio(symbols)
    telegram_notifier.send_message(format_weekly_telegram_report(result))
    return result


def check_daily_portfolio_changes(symbols: Optional[list[str]] = None) -> Optional[str]:
    """Bugünkü veriyi son haftalık konsensüs portföyle kıyaslar, değişiklikleri bildirir."""
    last = load_last_weekly_portfolio()
    if not last:
        logger.info("Kayıtlı haftalık portföy yok; günlük karşılaştırma atlanıyor.")
        return None

    symbols = symbols or DEFAULT_WATCHLIST
    finlab_db = load_finlab_data()
    df = get_indicators_batch(symbols, finlab_db)
    if df.empty:
        return None

    candidates = df[df.apply(lambda r: _passes_base_filter(r.to_dict()), axis=1)]
    today_symbols = set(candidates["Symbol"])
    last_symbols = {c["symbol"] for c in last["consensus_portfolio"]}

    new_entries = today_symbols - last_symbols
    dropped = last_symbols - today_symbols
    if not new_entries and not dropped:
        logger.info("Günlük portföy karşılaştırması: değişiklik yok.")
        return None

    lines = [f"🔄 *GÜNLÜK PORTFÖY REVİZYON BÜLTENİ* — {datetime.now().strftime('%d.%m.%Y')}"]
    if new_entries:
        lines.append("\n➕ *Yeni uygun hisseler:* " + ", ".join(sorted(new_entries)))
    if dropped:
        lines.append("\n➖ *Filtreden düşen hisseler:* " + ", ".join(sorted(dropped)))
    lines.append("\n_Cuma günü bir sonraki haftalık AI portföyünde bu değişiklikler yeniden değerlendirilecek._")

    text = "\n".join(lines)
    telegram_notifier.send_message(text)
    return text


if __name__ == "__main__":
    res = run_friday_job()
    print(format_weekly_telegram_report(res))
