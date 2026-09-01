"""
scheduler_manager.py
---------------------
BIST seans saatleri (hafta içi 10:00 - 18:00 Istanbul saati), resmi tatil kontrolleri
ve botun tekil çalışma (PID singleton lock) güvenlik mekanizması.
"""

from __future__ import annotations

import atexit
import logging
import os
import sys
from datetime import datetime, time as dtime
from pathlib import Path

import pytz

logger = logging.getLogger("scheduler_manager")

TR_TZ = pytz.timezone("Europe/Istanbul")

# BIST Resmi Seans Saatleri: Hafta İçi 10:00 - 18:00
MARKET_OPEN = dtime.fromisoformat(os.environ.get("BIST_MARKET_OPEN", "10:00"))
MARKET_CLOSE = dtime.fromisoformat(os.environ.get("BIST_MARKET_CLOSE", "18:00"))

LOCK_FILE = Path(os.environ.get("BOT_LOCK_FILE", str(Path(__file__).parent / "bot.lock")))

try:
    import holidays as holidays_lib
    _TR_HOLIDAYS = holidays_lib.Turkey()
except ImportError:
    logger.warning("`holidays` paketi bulunamadı; resmi tatil kontrolü varsayılan pasif.")
    _TR_HOLIDAYS = {}


def now_tr() -> datetime:
    """Türkiye saat dilimine (Europe/Istanbul) göre anlık zamanı döndürür."""
    return datetime.now(TR_TZ)


def is_trading_day(dt: datetime | None = None) -> bool:
    """Hafta sonu (Cumartesi/Pazar) ve resmi tatil değilse True döner."""
    dt = dt or now_tr()
    if dt.weekday() >= 5:  # 5=Cumartesi, 6=Pazar
        return False
    if dt.date() in _TR_HOLIDAYS:
        return False
    return True


def is_market_open(dt: datetime | None = None) -> bool:
    """BIST seans saatleri içinde mi (10:00 - 18:00, iş günü)?"""
    dt = dt or now_tr()
    if not is_trading_day(dt):
        return False
    return MARKET_OPEN <= dt.time() <= MARKET_CLOSE


def seconds_until_market_open(dt: datetime | None = None) -> int:
    dt = dt or now_tr()
    target = dt.replace(hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute, second=0, microsecond=0)
    if dt.time() > MARKET_OPEN:
        target = target.replace(day=target.day + 1)
    return max(0, int((target - dt).total_seconds()))


def acquire_singleton_lock(lock_path: Path = LOCK_FILE) -> bool:
    """
    PID tabanlı tekil çalışma kilidi (Singleton Lock).
    Aynı anda birden fazla bot sürecinin çalışmasını engeller.
    """
    if lock_path.exists():
        try:
            existing_pid = int(lock_path.read_text().strip())
            os.kill(existing_pid, 0)
            logger.warning("Bot zaten PID=%s ile çalışıyor. Yeni süreç sonlandırılıyor.", existing_pid)
            return False
        except (ValueError, ProcessLookupError, PermissionError, FileNotFoundError):
            logger.info("Eski/geçersiz kilit dosyası bulundu, temizleniyor ve devralınıyor.")

    try:
        lock_path.write_text(str(os.getpid()))
        atexit.register(_release_lock, lock_path)
        return True
    except Exception as e:
        logger.error("Kilit dosyası oluşturulamadı: %s", e)
        return True


def _release_lock(lock_path: Path = LOCK_FILE) -> None:
    try:
        if lock_path.exists() and lock_path.read_text().strip() == str(os.getpid()):
            lock_path.unlink()
    except OSError:
        pass
