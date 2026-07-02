import hashlib
import json
import logging
import tarfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from uuid import uuid4

from ..config import Settings
from ..db import get_connection
from ..repositories import now_utc
from ..storage import get_object_storage


logger = logging.getLogger(__name__)


def create_database_backup(settings: Settings) -> list[str]:
    now = datetime.now(UTC)
    keys = [f"backups/daily/ayqm-{now:%Y-%m-%d}.tar.gz"]
    if now.day == 1:
        keys.append(f"backups/monthly/ayqm-{now:%Y-%m}.tar.gz")
    with TemporaryDirectory(prefix="ayqm-backup-") as temporary:
        root = Path(temporary)
        export_dir = root / "database"
        with get_connection() as conn:
            conn.execute("CHECKPOINT")
            escaped = str(export_dir).replace("'", "''")
            conn.execute(
                f"EXPORT DATABASE '{escaped}' (FORMAT parquet, COMPRESSION zstd)"
            )
        manifest = {
            "created_at": now.isoformat(),
            "database": settings.database_path.name,
            "format": "duckdb-export-parquet",
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        archive = root / "backup.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            output.add(export_dir, arcname="database")
            output.add(root / "manifest.json", arcname="manifest.json")
        checksum = hashlib.sha256()
        with archive.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                checksum.update(chunk)
        digest = checksum.hexdigest()
        size = archive.stat().st_size
        storage = get_object_storage(settings)
        for key in keys:
            storage.put_file(key, archive, "application/gzip")
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO backup_records VALUES (?, ?, ?, ?, ?)",
                    [str(uuid4()), key, digest, size, now_utc()],
                )
    return keys


def _backup_loop(settings: Settings) -> None:
    while True:
        now = datetime.now(UTC)
        target = now.replace(hour=settings.backup_hour_utc, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        time.sleep(max(1, (target - now).total_seconds()))
        try:
            create_database_backup(settings)
        except Exception:
            logger.exception("Daily database backup failed")
            continue


def start_backup_scheduler(settings: Settings) -> None:
    Thread(target=_backup_loop, args=(settings,), name="ayqm-backups", daemon=True).start()
