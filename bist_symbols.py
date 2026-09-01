"""
bist_symbols.py
----------------
Borsa İstanbul (BIST) Tüm Hisseler Evreni ve Sektör Haritası Modülü.

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

# Borsa İstanbul Aktif Tüm Hisseler Havuzu (~540 Hisse)
ALL_BIST_SYMBOLS: list[str] = [
    "AAVTUR", "AAVTUR", "ADELE", "ADESE", "AEFES", "AFYON", "AGESA", "AGHOL", "AGROT", "AHGAZ",
    "AKBNK", "AKCNS", "AKENR", "AKFGY", "AKFYE", "AKGRT", "AKMGY", "AKSA", "AKSEN", "AKSGY",
    "AKSUE", "AKTVF", "ALARK", "ALBRK", "ALCAR", "ALCTL", "ALFAS", "ALGYO", "ALKA", "ALMAD",
    "ALTNY", "ALVES", "ANELE", "ANGEN", "ANHYT", "ANSGR", "ARASE", "ARCLK", "ARDYZ", "ARENA",
    "ARSAN", "ARTMS", "ARZUM", "ASELS", "ASGYO", "ASTOR", "ASUZU", "ATAGY", "ATAKP", "ATATP",
    "ATEKS", "ATSYH", "AVGYO", "AVHOL", "AVOD", "AVTUR", "AYCES", "AYDEM", "AYEN", "AYGAZ",
    "AZTEK", "BAGFS", "BAKAB", "BALAT", "BANVT", "BARMA", "BASGZ", "BASCM", "BAYRK", "BEVT",
    "BEGYO", "BERA", "BEYAZ", "BFREN", "BIENP", "BIGCHEFS", "BIMAS", "BINHO", "BIOEN", "BIZIM",
    "BJKAS", "BLCYT", "BMSCH", "BMSTL", "BNTAS", "BOBET", "BORLS", "BOSSA", "BRISA", "BRKO",
    "BRKSN", "BRKVY", "BRLSM", "BRMEN", "BRSAN", "BRYAT", "BSOKE", "BTCIM", "BUCIM", "BURCE",
    "BURVA", "BVSAN", "BYDNR", "CANTE", "CASA", "CATO", "CCOLA", "CELHA", "CEMAS", "CEMTS",
    "CMBTN", "CMENT", "CONSE", "COSMO", "CRFSA", "CRDFA", "CUSAN", "CVKMD", "CWENE", "DAGI",
    "DAPGM", "DARDL", "DGATE", "DGGYO", "DITAS", "DMRGD", "DMSAS", "DNISI", "DOAS", "DOCO",
    "DOGUB", "DOHOL", "DOKTA", "DURDO", "DYOBY", "DZGYO", "EBEBK", "ECILC", "ECZYT", "EDATA",
    "EDIP", "EGEEN", "EGGUB", "EGPRO", "EGSER", "EKGYO", "EKIZ", "EKSUN", "ELITE", "EMKEL",
    "EMNIS", "ENJSA", "ENKAI", "ENTRA", "EPLAS", "ERBOS", "EREGL", "ERSU", "ESCAR", "ESCOM",
    "ESEN", "ETILR", "EUPWR", "EUREK", "EYGYO", "FADE", "FENER", "FLAP", "FMIZP", "FONET",
    "FORMT", "FORTE", "FRIGO", "FROTO", "FZLGY", "GARAN", "GARFA", "GEDIK", "GEDZA", "GENKE",
    "GENTSH", "GESAN", "GIPTA", "GLBMD", "GLCVY", "GLYHO", "GMTAS", "GOKNR", "GOLTS", "GOODY",
    "GOZDE", "GRNYO", "GRSEL", "GRTRK", "GSDDE", "GSDHO", "GSRAY", "GUBRF", "GWIND", "GZNMI",
    "HALKB", "HATEK", "HATSN", "HDFGS", "HEKTS", "HKTM", "HLGYO", "HUBVC", "HUNER", "HURGZ",
    "ICBCT", "ICUGS", "IDGYO", "IEYHO", "IHAAS", "IHEVA", "IHGZT", "IHLGM", "IHLAS", "INGRM",
    "INTEM", "INVEO", "INVES", "IPEKE", "ISATR", "ISBIR", "ISBTR", "ISCTR", "ISDMR", "ISFIN",
    "ISGSY", "ISGYO", "ISKPL", "ISKUR", "ISMEN", "ISSEN", "ITEKH", "ITZGY", "IZENR", "IZINV",
    "IZMDC", "JANTS", "KAFEIN", "KLKIM", "KARSN", "KARTN", "KATES", "KATMR", "KAYSE", "KBORU",
    "KCAER", "KCHOL", "KENT", "KRTEK", "KERVT", "KFEIN", "KGYO", "KIMMR", "KLGYO", "KLMSN",
    "KLSER", "KLYSN", "KMFIN", "KNFRT", "KONTR", "KONYA", "KORDS", "KOZAL", "KOZAA", "KRDMA",
    "KRDMB", "KRDMD", "KRGYO", "KRPLS", "KRSTN", "KSTUR", "KTLEV", "KTSKR", "KUTPO", "KUZEY",
    "KZBGY", "KZGYO", "LIDER", "LIDFA", "LINK", "LKMNH", "LMKDC", "LOGAN", "LOGO", "LRVGY",
    "LUKSK", "MAALT", "MACKO", "MAKIM", "MAKTK", "MANAS", "MARKA", "MAVI", "MEDTR", "MEGAP",
    "MEGMT", "MEPET", "MERCN", "MERIT", "MERKO", "METRO", "METUR", "MHRGY", "MIATK", "MGROS",
    "MIPAZ", "MMCAS", "MNDTR", "MOBTL", "MOGAN", "MPARK", "MRGYO", "MRSHL", "MSGYO", "MTRKS",
    "MTRYO", "MZHLD", "NATEN", "NETAS", "NIBAS", "NTHOL", "NUGYO", "NUHCM", "OBAMS", "OBASE",
    "ODAS", "OFCAD", "OFSYM", "ONCSM", "ORCA", "ORMA", "ORTAS", "OTKAR", "OTTO", "OYAKC",
    "OYLUM", "OYYAT", "OZKGY", "OZRDN", "OZSUB", "PAGYO", "PAMEL", "PAPIL", "PARSN", "PASEU",
    "PENGD", "PENTA", "PETKM", "PETRK", "PGSUS", "PINAR", "PKART", "PKENT", "PLTUR", "PNLSN",
    "POLHO", "POLTK", "PRDGS", "PRKAB", "PRKME", "PRZMA", "PSGYO", "QNBFB", "QNBFL", "QUAGR",
    "RALYH", "RAYSG", "REEDR", "RNPOL", "RODRG", "ROYAL", "RTALB", "RUBNS", "RYGYO", "RYSAS",
    "SAFKR", "SAHOL", "SAMAT", "SANEL", "SANFM", "SANKO", "SARKY", "SASA", "SAYAS", "SDTTR",
    "SEGMN", "SEKFK", "SEKUR", "SELEC", "SELVA", "SEYKM", "SILVR", "SISE", "SKBNK", "SKTAS",
    "SMART", "SMRTG", "SNAYS", "SNICA", "SNKRN", "SNPAM", "SODSN", "SOKM", "SONME", "SRVGY",
    "SUMAS", "SUNTK", "SURGY", "SUWEN", "TATEN", "TATGD", "TAVHL", "TCELL", "TDGYO", "TEKTU",
    "TERA", "TETMT", "TEZOL", "TGBTN", "TGSAS", "THYAO", "TKFEN", "TKNSA", "TLMAN", "TMPOL",
    "TMSN", "TNZTP", "TOASO", "TRGYO", "TLGA", "TRCAS", "TRILC", "TSKB", "TSPOR", "TTKOM",
    "TTRAK", "TUCLK", "TUPRS", "TURGG", "TURSG", "UFUK", "ULAS", "ULKER", "UNLU", "USAK",
    "VAKBN", "VAKFN", "VAKKO", "VANGD", "VBTYZ", "VERTU", "VERUS", "VESBE", "VESTL", "VKFYO",
    "VKGYO", "YAPRK", "YATAS", "YAYLA", "YBTAS", "YEOTK", "YGYO", "YKBNK", "YNKAS", "YONGA",
    "YOTAS", "YATAS", "YYLGD", "ZEDUR", "ZOREN", "ZRGYO"
]

SECTOR_MAP: dict[str, str] = {
    "THYAO": "Ulaştırma", "PGSUS": "Ulaştırma", "TAVHL": "Ulaştırma", "TLMAN": "Ulaştırma", "CLEBI": "Ulaştırma",
    "ASELS": "Savunma/Sanayi", "KONTR": "Savunma/Sanayi", "SDTTR": "Savunma/Sanayi", "FORTE": "Savunma/Teknoloji",
    "SASA": "Kimya", "PETKM": "Kimya", "GUBRF": "Kimya", "AKSA": "Kimya", "BAGFS": "Kimya", "HEKTS": "Tarım Kimyası",
    "KCHOL": "Holding", "SAHOL": "Holding", "ALARK": "Holding", "AGHOL": "Holding", "DOHOL": "Holding", "BERA": "Holding",
    "TUPRS": "Enerji", "ENJSA": "Enerji", "ODAS": "Enerji", "AKSEN": "Enerji", "CANTE": "Enerji", "CWENE": "Enerji", "ASTOR": "Enerji", "GESAN": "Enerji", "EUPWR": "Enerji", "YEOTK": "Enerji", "GWIND": "Enerji", "AYDEM": "Enerji",
    "BIMAS": "Perakende", "MGROS": "Perakende", "SOKM": "Perakende", "ULKER": "Gıda/Perakende", "CCOLA": "İçecek", "AEFES": "İçecek", "EBEBK": "Perakende", "CRFSA": "Perakende",
    "EREGL": "Demir-Çelik", "KRDMD": "Demir-Çelik", "ISDMR": "Demir-Çelik", "KCAER": "Demir-Çelik", "CEMTS": "Demir-Çelik",
    "KOZAL": "Madencilik", "KOZAA": "Madencilik", "IPEKE": "Madencilik", "CVKMD": "Madencilik",
    "SISE": "Cam/Sanayi",
    "AKBNK": "Bankacılık", "GARAN": "Bankacılık", "ISCTR": "Bankacılık", "YKBNK": "Bankacılık", "HALKB": "Bankacılık", "VAKBN": "Bankacılık", "ALBRK": "Bankacılık", "TSKB": "Bankacılık", "SKBNK": "Bankacılık",
    "TCELL": "Telekom", "TTKOM": "Telekom",
    "FROTO": "Otomotiv", "TOASO": "Otomotiv", "DOAS": "Otomotiv", "OTKAR": "Otomotiv", "TTRAK": "Otomotiv", "ASUZU": "Otomotiv", "KARSN": "Otomotiv",
    "VESTL": "Elektronik", "ARCLK": "Dayanıklı Tüketim", "VESBE": "Dayanıklı Tüketim",
    "EKGYO": "Gayrimenkul", "ISGYO": "Gayrimenkul", "PSGYO": "Gayrimenkul", "AKFGY": "Gayrimenkul", "SNGYO": "Gayrimenkul", "OZKGY": "Gayrimenkul",
    "MIATK": "Teknoloji", "REEDR": "Teknoloji", "ARDYZ": "Teknoloji", "KONTR": "Teknoloji", "LOGO": "Teknoloji", "VBTYZ": "Teknoloji",
    "CIMSA": "Çimento", "OYAKC": "Çimento", "BOBET": "Çimento", "BUCIM": "Çimento", "AKCNS": "Çimento", "AFYON": "Çimento", "BTCIM": "Çimento"
}


def get_sector(symbol: str) -> str:
    clean_sym = symbol.replace("BIST:", "").replace(".IS", "").upper()
    return SECTOR_MAP.get(clean_sym, "Genel Sanayi / Finans")


def get_symbol_universe(all_stocks: bool = False) -> list[str]:
    """Tüm BIST hisselerini veya varsayılan BIST 100 havuzunu döndürür."""
    if all_stocks:
        # Çift kayıtları temizle
        seen = set()
        unique_syms = []
        for s in ALL_BIST_SYMBOLS:
            clean_s = s.replace("BIST:", "").replace(".IS", "").upper()
            if clean_s not in seen:
                seen.add(clean_s)
                unique_syms.append(clean_s)
        return unique_syms
    return DEFAULT_WATCHLIST
