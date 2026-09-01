"""
watchdog.py
===========
Akıllı Hata Yönetimi ve Öz-İyileştirmeli Gözetçi Servisi (Self-Healing Watchdog).

Özellikler:
1. Üstel Geri Çekilme (Exponential Backoff): TradingView API ağ ve limit hatalarında
   5s -> 15s -> 30s artan aralıklarla otomatik yeniden deneme.
2. Otonom Kurtarma (Self-Healing): Beklenmeyen kritik istisnalarda logları kaydetme,
   bayat PID kilitlerini (bot.lock) temizleme, Telegram acil uyarı gönderme ve botu
   güvenli bir şekilde yeniden başlatma.
"""

import sys
import io
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time
import logging
import traceback
from pathlib import Path
from typing import Callable, Any

from telegram_notifier import send_message
from scheduler_manager import LOCK_FILE

logger = logging.getLogger("watchdog")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

ERROR_LOG_FILE = DATA_DIR / "bot_error.log"


def exponential_backoff_retry(func: Callable, max_retries: int = 3, initial_delay: float = 5.0) -> Any:
    """TradingView API ve ağ istekleri için üstel geri çekilmeli yeniden deneme fonksiyonu."""
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            logger.warning(f"⚠️ Bağlantı hatası deneme ({attempt}/{max_retries}) [{e}]. {delay} sn bekleniyor...")
            if attempt == max_retries:
                raise e
            time.sleep(delay)
            delay *= 3.0  # 5s -> 15s -> 45s


def log_exception_details(exc: Exception):
    """Kritik çökme ayrıntılarını data/bot_error.log dosyasına yazar."""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        tb_str = traceback.format_exc()
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n================ [{timestamp}] KRİTİK HATA ================\n")
            f.write(f"Hata Türü: {type(exc).__name__}: {exc}\n")
            f.write(tb_str)
            f.write("=================================================================\n")
    except Exception as e:
        logger.error("Hata günlüğü yazılamadı: %s", e)


def cleanup_stale_lock():
    """Çökme durumunda bayat PID kilit dosyasını temizler."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
            logger.info("🧹 Bayat PID kilit dosyası (%s) temizlendi.", LOCK_FILE)
    except Exception as e:
        logger.warning("Kilit dosyası temizleme hatası: %s", e)


def run_with_watchdog(target_func: Callable, *args, **kwargs):
    """
    Ana bot döngüsünü sarmalayan otonom kurtarma ve gözetçi servis.
    Çökme durumunda sistemi kurtarır ve yeniden başlatır.
    """
    retry_count = 0
    max_consecutive_crashes = 10

    while True:
        try:
            logger.info("🛡️ Watchdog Gözetçi Servisi Aktif. Ana Bot Başlatılıyor...")
            target_func(*args, **kwargs)
            # Başarılı tamamlama
            break
        except KeyboardInterrupt:
            logger.info("🛑 Kullanıcı tarafından durduruldu. Watchdog sonlandırılıyor.")
            cleanup_stale_lock()
            sys.exit(0)
        except Exception as exc:
            retry_count += 1
            logger.error("🚨 CRITICAL BOT ERROR: %s", exc)
            log_exception_details(exc)
            cleanup_stale_lock()

            alert_msg = (
                f"🚨 *BIST BOTU OTOMATİK KURTARMA (SELF-HEALING)*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ *Kritik Hata:* `{type(exc).__name__}: {exc}`\n"
                f"🔄 *Kurtarma Denemesi:* `{retry_count}/{max_consecutive_crashes}`\n"
                f"💡 *Durum:* Bayat kilit temizlendi, bot 10 saniye içinde yeniden başlatılıyor."
            )
            send_message(alert_msg)

            if retry_count >= max_consecutive_crashes:
                logger.critical("❌ Ardışık maksimum çökme sınırına ulaşıldı. Bot durduruldu.")
                break

            time.sleep(10.0)


if __name__ == "__main__":
    def dummy_fail():
        print("Test çalışıyor...")
        raise ValueError("Test Hatası!")

    run_with_watchdog(dummy_fail)
