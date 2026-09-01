# BIST Algoritmik Ticaret ve AI Portföy Botu

## Kurulum

```bash
pip install -r requirements.txt
cp .env.example .env      # .env dosyasini doldurun (Telegram token/chat_id vb.)
```

## Kullanım

```bash
python bot.py --once          # Tek seferlik anlık tarama
python bot.py --report        # Günlük özet rapor (Telegram'a gönderilir)
python bot.py --weekly-ai     # Manuel haftalık AI portföy raporu üretimi
python bot.py                 # Zamanlayıcı modu: seans saatleri + Cuma 12:30 AI görevi
```

## Dosya Yapısı

| Dosya                     | Görev                                                              |
|----------------------------|---------------------------------------------------------------------|
| `indicators.py`            | tradingview-ta + Finlab veri birleştirme katmanı                    |
| `ai_portfolio_manager.py`  | 5 AI persona, sektör-kontrollü haftalık portföy üretimi              |
| `bot.py`                   | Ana CLI / zamanlayıcı, sinyal mantığı, grafik + Telegram gönderimi   |
| `scheduler_manager.py`     | BIST seans/tatil kontrolü, tekil-örnek (singleton) kilidi            |
| `telegram_notifier.py`     | Telegram mesaj/fotoğraf gönderim yardımcı modülü                     |
| `bist_symbols.py`          | İzleme listesi + sektör haritası (SECTOR_MAP)                        |
| `finlab_data.json`         | Örnek Finlab temel analiz verisi (gerçek veriyle değiştirin)         |

## Önemli Mimari Notlar

- **Veri kaynağı:** Yalnızca `tradingview-ta` (screener="turkey", exchange="BIST"). `yfinance` kullanılmaz.
- **Vol_SMA20 / grafikler:** tradingview-ta yalnızca anlık veri döndürür; hacim ortalaması ve
  fiyat grafiği botun kendi çalışma geçmişinden (`data/`) zamanla birikir. İlk ~20 çalıştırmaya
  kadar bu alanlar `None` dönebilir, sinyal mantığı bunu güvenle atlar.
- **Sharpe optimizasyonu:** Gerçek kovaryans tabanlı optimizasyon için geçmiş getiri serisi
  gerekir (tradingview-ta bunu sağlamaz). Bunun yerine hisse başına %25 ve sektör başına %40
  ağırlık tavanlı, skor-orantılı bir dağıtım proxy olarak kullanılır.
- **5 AI persona:** Her biri deterministik kural-tabanlı skorlama ile her zaman çalışır.
  `ANTHROPIC_API_KEY` tanımlıysa ek olarak gerçek Claude sorgusuyla nitel gerekçe üretilir.
- **Güvenli arka plan çalıştırma:** `scheduler_manager.py` içinde Linux (systemd) ve Windows
  (Task Scheduler + pythonw) için "sonsuz terminal açmayan" başlatma örnekleri bulunur;
  ayrıca PID kilidi ile aynı botun birden fazla kez başlatılması engellenir.

## Test

Tüm modüller sözdizimi, import bütünlüğü, persona/sektör ağırlıklandırma ve sinyal mantığı
açısından sahte veriyle test edilmiştir (bkz. teslimat notları).
