"""Shared limits for untrusted backup uploads.

Starlette's multipart parser writes file parts to a spooled temp file with no
size cap before the route runs. The upload guard therefore stops reading once
the body exceeds the configured ceiling, and restore keeps two more bounded
copies (the parser spool and the staged file). Disk checks reserve room for
all three.
"""
from app.core.config import settings

# Multipart boundaries and the restore form fields sit beside the zip bytes.
MULTIPART_OVERHEAD_BYTES = 256 * 1024
DISK_RESERVE_BYTES = 10 * 1024 * 1024
DISK_COPY_FACTOR = 3

UPLOAD_TOO_LARGE = "Backup exceeds the upload size limit"
UPLOAD_TIMED_OUT = "Backup upload timed out"
UPLOAD_NO_SPACE = "Insufficient disk space for backup upload"
INVALID_CONTENT_LENGTH = "Invalid Content-Length"


def upload_body_limit() -> int:
    """HTTP body ceiling: the zip limit plus a small multipart allowance."""
    return settings.BACKUP_MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES


def disk_required_for(num_bytes: int) -> int:
    """Free space required before accepting ``num_bytes`` of upload body."""
    return num_bytes * DISK_COPY_FACTOR + DISK_RESERVE_BYTES
