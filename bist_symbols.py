"""
bist_symbols.py
----------------
BIST 100 Gün İçi Al-Sat Botu Hisse Sembol Havuzu ve Sektör Haritası.

NOT: tradingview-ta'da sembol, BORSA ÖN EKİ OLMADAN (ör. "THYAO") verilir;
exchange="BIST", screener="turkey" parametreleri TA_Handler / get_multiple_analysis
içinde ayrıca belirtilir.
"""

DEFAULT_WATCHLIST: list[str] = [
    "AGHOL", "AGROT", "AHGAZ", "AKBNK", "AKCNS", "AKFGY", "AKFYE", "AKSA", "AKSEN", "ALARK",
    "ALBRK", "ALFAS", "ANSGR", "ARCLK", "ASELS", "ASTOR", "BERA", "BIENP", "BIMAS", "BINHO",
    "BOBET", "BRSAN", "BRYAT", "BUCIM", "CANTE", "CCOLA", "CIMSA", "CWENE", "DOAS", "DOHOL",
    "EBEBK", "ECILC", "ECZYT", "EGEEN", "EKGYO", "ENJSA", "ENKAI", "EREGL", "EUPWR", "EUREK",
    "FROTO", "GARAN", "GESAN", "GUBRF", "HALKB", "HEKTS", "ISCTR", "ISGYO", "ISMEN", "KAYSE",
    "KCAER", "KCHOL", "KLSER", "KONTR", "KORDS", "KOZAL", "KOZAA", "KRDMD", "MAVI", "MHRGY",
    "MIATK", "MGROS", "ODAS", "OTKAR", "OYAKC", "PETKM", "PGSUS", "PSGYO", "REEDR", "SAHOL",
    "SASA", "SDTTR", "SISE", "SKBNK", "SOKM", "TABGD", "TAVHL", "TCELL", "THYAO", "TKFEN",
    "TOASO", "TSKB", "TTKOM", "TTRAK", "TUPRS", "TURSG", "ULKER", "VAKBN", "VESBE", "VESTL",
    "YEOTK", "YKBNK", "ZOREN"
]

SECTOR_MAP: dict[str, str] = {
    "THYAO": "Ulaştırma", "PGSUS": "Ulaştırma", "TAVHL": "Ulaştırma",
    "ASELS": "Savunma/Sanayi", "KONTR": "Savunma/Sanayi", "SDTTR": "Savunma/Sanayi",
    "SASA": "Kimya", "PETKM": "Kimya", "GUBRF": "Kimya", "AKSA": "Kimya",
    "KCHOL": "Holding", "SAHOL": "Holding", "ALARK": "Holding", "AGHOL": "Holding", "DOHOL": "Holding",
    "TUPRS": "Enerji", "ENJSA": "Enerji", "ODAS": "Enerji", "AKSEN": "Enerji", "CANTE": "Enerji", "CWENE": "Enerji", "ASTOR": "Enerji", "GESAN": "Enerji", "EUPWR": "Enerji", "YEOTK": "Enerji",
    "BIMAS": "Perakende", "MGROS": "Perakende", "SOKM": "Perakende", "ULKER": "Gıda/Perakende", "CCOLA": "İçecek", "EBEBK": "Perakende",
    "EREGL": "Demir-Çelik", "KRDMD": "Demir-Çelik", "ISDMR": "Demir-Çelik", "KCAER": "Demir-Çelik",
    "KOZAL": "Madencilik", "KOZAA": "Madencilik",
    "SISE": "Cam/Sanayi",
    "AKBNK": "Bankacılık", "GARAN": "Bankacılık", "ISCTR": "Bankacılık", "YKBNK": "Bankacılık", "HALKB": "Bankacılık", "VAKBN": "Bankacılık", "ALBRK": "Bankacılık", "TSKB": "Bankacılık",
    "TCELL": "Telekom", "TTKOM": "Telekom",
    "FROTO": "Otomotiv", "TOASO": "Otomotiv", "DOAS": "Otomotiv", "OTKAR": "Otomotiv", "TTRAK": "Otomotiv",
    "VESTL": "Elektronik", "ARCLK": "Dayanıklı Tüketim", "VESBE": "Dayanıklı Tüketim",
    "HEKTS": "Tarım Kimyası",
    "EKGYO": "Gayrimenkul", "ISGYO": "Gayrimenkul", "PSGYO": "Gayrimenkul", "AKFGY": "Gayrimenkul",
    "MIATK": "Teknoloji", "REEDR": "Teknoloji",
    "CIMSA": "Çimento", "OYAKC": "Çimento", "BOBET": "Çimento", "BUCIM": "Çimento", "AKCNS": "Çimento"
}

def get_sector(symbol: str) -> str:
    clean_sym = symbol.replace("BIST:", "").replace(".IS", "").upper()
    return SECTOR_MAP.get(clean_sym, "Diğer")
