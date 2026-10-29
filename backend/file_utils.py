"""
backend/file_utils.py — Robust Atomic File Persistence & Disk Space Utilities.

Protects against data corruption and file wiping during disk-space exhaustion (ENOSPC)
or container write I/O errors (EIO) by using atomic tempfile writes and fsync before rename.
"""

import os
import json
import shutil
import tempfile
import logging
from typing import Any, Optional

logger = logging.getLogger("hermes.file_utils")


def check_disk_space(path: str, min_free_mb: int = 500) -> bool:
    """
    Checks available disk space at the specified path.
    Returns True if free space >= min_free_mb, False otherwise.
    """
    try:
        usage = shutil.disk_usage(path)
        free_mb = usage.free / (1024 * 1024)
        if free_mb < min_free_mb:
            logger.warning(
                "Low disk space warning on %s: %.1f MB available (threshold: %d MB)",
                path, free_mb, min_free_mb
            )
            return False
        return True
    except Exception as e:
        logger.debug("Failed to check disk space on %s: %s", path, e)
        return True


def atomic_write_json(filepath: str, data: Any, indent: Optional[int] = None) -> bool:
    """
    Atomically writes JSON-serializable data to `filepath`.
    Writes to a temporary file in the same directory, flushes, syncs to disk,
    and uses os.replace to atomically update the target file.
    
    If writing fails (e.g., ENOSPC or EIO), the target file remains intact.
    Returns True on success, False on failure.
    """
    target_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(target_dir, exist_ok=True)
    
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=target_dir,
            prefix=f".{os.path.basename(filepath)}.tmp_",
            delete=False,
            encoding="utf-8"
        ) as tf:
            tmp_path = tf.name
            json.dump(data, tf, indent=indent)
            tf.flush()
            os.fsync(tf.fileno())

        os.replace(tmp_path, filepath)
        return True
    except Exception as e:
        logger.error("Failed atomic JSON write to %s: %s", filepath, e)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False
