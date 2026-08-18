"""
scheduler_manager.py
---------------------
BIST resmi seans saatleri, hafta sonu / resmi tatil kontrolü ve botun
bilgisayar açılışında YİNELENEN / SONSUZ TERMİNAL PENCERESİ üretmeden
tek bir arka plan sürecinde güvenle çalışmasını sağlayan kilit mekanizması.

Kullanım:
    from scheduler_manager import is_trading_day, is_market_open, acquire_singleton_lock

    if not acquire_singleton_lock():
        sys.exit(0)   # zaten çalışan bir örnek var, sessizce çık
    ...
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

# BIST 2016'dan bu yana tek (kesintisiz) seans uygular: 10:00 - 18:00
MARKET_OPEN = dtime.fromisoformat(os.environ.get("BIST_MARKET_OPEN", "10:00"))
MARKET_CLOSE = dtime.fromisoformat(os.environ.get("BIST_MARKET_CLOSE", "18:00"))

LOCK_FILE = Path(os.environ.get("BOT_LOCK_FILE", str(Path(__file__).parent / "bot.lock")))

try:
    import holidays as holidays_lib
    _TR_HOLIDAYS = holidays_lib.Turkey()
except ImportError:  # pragma: no cover
    logger.warning("`holidays` paketi bulunamadı; resmi tatil kontrolü devre dışı. "
                    "pip install holidays komutunu çalıştırın.")
    _TR_HOLIDAYS = {}


# --------------------------------------------------------------------------- #
# Seans / takvim kontrolleri
# --------------------------------------------------------------------------- #
def now_tr() -> datetime:
    return datetime.now(TR_TZ)


def is_trading_day(dt: datetime | None = None) -> bool:
    """Hafta sonu değil ve resmi tatil değilse True döner."""
    dt = dt or now_tr()
    if dt.weekday() >= 5:  # 5=Cumartesi, 6=Pazar
        return False
    if dt.date() in _TR_HOLIDAYS:
        return False
    return True


def is_market_open(dt: datetime | None = None) -> bool:
    """BIST seans saatleri içinde mi (10:00-18:00, iş günü)?"""
    dt = dt or now_tr()
    if not is_trading_day(dt):
        return False
    return MARKET_OPEN <= dt.time() <= MARKET_CLOSE


def is_friday_afternoon_window(dt: datetime | None = None,
                                target: dtime = dtime.fromisoformat("12:30"),
                                tolerance_minutes: int = 5) -> bool:
    """Cuma 12:30 (± tolerans) penceresinde miyiz? Haftalık AI raporu tetikleyicisi için."""
    dt = dt or now_tr()
    if dt.weekday() != 4:  # 4 = Cuma
        return False
    minutes_diff = abs((dt.hour * 60 + dt.minute) - (target.hour * 60 + target.minute))
    return minutes_diff <= tolerance_minutes


def seconds_until_market_open(dt: datetime | None = None) -> int:
    dt = dt or now_tr()
    target = dt.replace(hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute, second=0, microsecond=0)
    if dt.time() > MARKET_OPEN:
        target = target.replace(day=target.day + 1)
    return max(0, int((target - dt).total_seconds()))


# --------------------------------------------------------------------------- #
# Tekil-örnek (singleton) kilidi
# --------------------------------------------------------------------------- #
def acquire_singleton_lock(lock_path: Path = LOCK_FILE) -> bool:
    """
    Botun aynı anda birden fazla kez (ör. bilgisayar her açılışta yeniden
    tetiklenen bir görev zamanlayıcısı yüzünden) başlatılmasını engeller.
    PID tabanlı kilit dosyası kullanır; kilit sahibi süreç artık çalışmıyorsa
    otomatik olarak devralınır (stale lock temizliği).

    Dönüş: True -> kilit alındı, çalışmaya devam et.
           False -> başka bir örnek zaten çalışıyor, bu süreç kendini
                    sonlandırmalı.
    """
    if lock_path.exists():
        try:
            existing_pid = int(lock_path.read_text().strip())
            os.kill(existing_pid, 0)  # süreç yaşıyor mu kontrolü (sinyal göndermez)
            logger.warning("Bot zaten PID=%s ile çalışıyor. Bu örnek sonlandırılıyor.", existing_pid)
            return False
        except (ValueError, ProcessLookupError, PermissionError, FileNotFoundError):
            logger.info("Eski/geçersiz kilit dosyası bulundu, temizleniyor ve devralınıyor.")

    lock_path.write_text(str(os.getpid()))
    atexit.register(_release_lock, lock_path)
    return True


def _release_lock(lock_path: Path = LOCK_FILE) -> None:
    try:
        if lock_path.exists() and lock_path.read_text().strip() == str(os.getpid()):
            lock_path.unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# İşletim sistemi başlangıcı için örnek (dokümantasyon amaçlı)
# --------------------------------------------------------------------------- #
"""
GÜVENLİ ARKA PLAN ÇALIŞTIRMA (bilgisayar açılışında sonsuz terminal döngüsü YOK):

Linux (systemd) — /etc/systemd/system/bist-bot.service:
    [Unit]
    Description=BIST Algoritmik Ticaret Botu
    After=network-online.target

    [Service]
    Type=simple
    WorkingDirectory=/opt/bist_bot
    ExecStart=/usr/bin/python3 /opt/bist_bot/bot.py
    Restart=on-failure
    RestartSec=30

    [Install]
    WantedBy=multi-user.target

    # Etkinleştirme:  sudo systemctl enable --now bist-bot.service
    # Bu yapı sürec tek başlatılır, çökerse yeniden başlatılır; asla
    # yinelenen terminal pencereleri açmaz.

Windows — Görev Zamanlayıcı (Task Scheduler):
    - Eylem: "pythonw.exe C:\\bist_bot\\bot.py"  (pythonw = konsol penceresi AÇMAZ)
    - Tetikleyici: "Oturum açılışında", tekrar ayarı KAPALI (tek seferlik başlatma)
    - "Zaten çalışıyorsa yeni örnek başlatma" seçeneği işaretli olmalı
    - Kod içindeki acquire_singleton_lock() bu davranışı ayrıca garanti eder.
"""
