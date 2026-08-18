"""
bist_symbols.py
----------------
Botun tarayacağı BIST hisse kodları listesi.
Gerçek kullanımda bu listeyi BIST30 / BIST100 tam listesiyle
veya kendi Finlab evreninizle değiştirin.

NOT: tradingview-ta'da sembol, BORSA ÖN EKİ OLMADAN (ör. "THYAO") verilir;
exchange="BIST" parametresi TA_Handler içinde ayrıca belirtilir.
"""

DEFAULT_WATCHLIST: list[str] = [
    "THYAO", "ASELS", "SASA", "KCHOL", "TUPRS", "BIMAS", "EREGL", "SISE",
    "AKBNK", "GARAN", "ISCTR", "PGSUS", "TCELL", "FROTO", "TOASO",
    "YKBNK", "VESTL", "ARCLK", "HEKTS", "KOZAL", "PETKM", "SAHOL",
    "TAVHL", "ENJSA", "MGROS", "ULKER", "KONTR", "ODAS", "GUBRF", "ALARK",
]

# Sektör bazlı çeşitlendirme/korelasyon kontrolü için kaba sınıflandırma.
# ai_portfolio_manager.py bunu portföyde tek bir sektörün ağırlık tavanını
# aşmasını (yüksek iç-korelasyon riskini) engellemek için kullanır.
SECTOR_MAP: dict[str, str] = {
    "THYAO": "Ulaştırma", "PGSUS": "Ulaştırma", "TAVHL": "Ulaştırma",
    "ASELS": "Savunma/Sanayi", "KONTR": "Savunma/Sanayi",
    "SASA": "Kimya", "PETKM": "Kimya", "GUBRF": "Kimya",
    "KCHOL": "Holding", "SAHOL": "Holding", "ALARK": "Holding",
    "TUPRS": "Enerji", "ENJSA": "Enerji", "ODAS": "Enerji",
    "BIMAS": "Perakende", "MGROS": "Perakende", "ULKER": "Perakende",
    "EREGL": "Demir-Çelik", "KOZAL": "Madencilik",
    "SISE": "Cam/Sanayi",
    "AKBNK": "Bankacılık", "GARAN": "Bankacılık", "ISCTR": "Bankacılık", "YKBNK": "Bankacılık",
    "TCELL": "Telekom",
    "FROTO": "Otomotiv", "TOASO": "Otomotiv", "VESTL": "Otomotiv/Elektronik", "ARCLK": "Dayanıklı Tüketim",
    "HEKTS": "Tarım Kimyası",
}


def get_sector(symbol: str) -> str:
    return SECTOR_MAP.get(symbol.upper(), "Diğer")
