"""
Log Retrieval API (Story 6.2, AC: #5)

Endpoints for querying and downloading application logs:
- GET /api/v1/logs - Query log entries with filtering
- GET /api/v1/logs/download - Download log file for specific date
"""
import os
import json
import logging
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/logs",
    tags=["logs"]
)

# Log directory path
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    'data', 'logs'
)


class LogEntry(BaseModel):
    """Single log entry from JSON log file"""
    timestamp: str
    level: str
    message: str
    module: Optional[str] = None
    logger: Optional[str] = None
    request_id: Optional[str] = None
    function: Optional[str] = None
    line: Optional[int] = None
    # Allow additional fields
    extra: Optional[dict] = Field(default_factory=dict)


class LogsResponse(BaseModel):
    """Response for log query endpoint"""
    entries: List[LogEntry]
    total: int
    limit: int
    offset: int
    has_more: bool


class LogFilesResponse(BaseModel):
    """Response for available log files endpoint"""
    files: List[str]
    directory: str


def _parse_log_line(line: str) -> Optional[dict]:
    """
    Parse a single JSON log line.

    Args:
        line: Raw log line from file

    Returns:
        Parsed log entry dict or None if parse fails
    """
    line = line.strip()
    if not line:
        return None

    try:
        return json.loads(line)
    except json.JSONDecodeError:
        # Not a JSON log line, skip
        return None


def _matches_filters(
    entry: dict,
    level: Optional[str],
    module: Optional[str],
    search: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date]
) -> bool:
    """
    Check if log entry matches filter criteria.

    Args:
        entry: Parsed log entry
        level: Filter by log level
        module: Filter by module name
        search: Search text in message
        start_date: Filter entries on or after this date
        end_date: Filter entries on or before this date

    Returns:
        True if entry matches all filters
    """
    # Level filter
    if level:
        entry_level = entry.get('level', '').upper()
        if entry_level != level.upper():
            return False

    # Module filter
    if module:
        entry_module = entry.get('module', '') or entry.get('logger', '')
        if module.lower() not in entry_module.lower():
            return False

    # Search filter
    if search:
        message = entry.get('message', '')
        if search.lower() not in message.lower():
            return False

    # Date filters
    if start_date or end_date:
        timestamp = entry.get('timestamp', '')
        if timestamp:
            try:
                entry_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date()
                if start_date and entry_date < start_date:
                    return False
                if end_date and entry_date > end_date:
                    return False
            except ValueError:
                pass  # Can't parse timestamp, skip date filter

    return True


def _read_log_entries(
    level: Optional[str] = None,
    module: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple[List[dict], int]:
    """
    Read and filter log entries from log files.

    Args:
        level: Filter by log level
        module: Filter by module name
        search: Search text in message
        start_date: Filter entries on or after this date
        end_date: Filter entries on or before this date
        limit: Maximum entries to return
        offset: Number of entries to skip

    Returns:
        Tuple of (list of matching entries, total count)
    """
    entries = []
    log_file = os.path.join(LOG_DIR, 'app.log')

    if not os.path.exists(log_file):
        return [], 0

    # Read all entries (in reverse order - newest first)
    all_entries = []
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                entry = _parse_log_line(line)
                if entry and _matches_filters(entry, level, module, search, start_date, end_date):
                    all_entries.append(entry)
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return [], 0

    # Reverse to get newest first
    all_entries.reverse()

    total = len(all_entries)

    # Apply pagination
    entries = all_entries[offset:offset + limit]

    return entries, total


@router.get("", response_model=LogsResponse)
async def get_logs(
    level: Optional[str] = Query(
        None,
        description="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    ),
    module: Optional[str] = Query(
        None,
        description="Filter by module name (partial match)"
    ),
    search: Optional[str] = Query(
        None,
        description="Search text in log messages"
    ),
    start_date: Optional[date] = Query(
        None,
        description="Filter entries on or after this date (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        None,
        description="Filter entries on or before this date (YYYY-MM-DD)"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of entries to return"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of entries to skip"
    )
):
    """
    Query log entries with filtering and pagination.

    Returns log entries in JSON format with support for filtering by:
    - Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - Module name (partial match)
    - Search text in messages
    - Date range

    Results are returned in reverse chronological order (newest first).

    **Example:**
    ```
    GET /api/v1/logs?level=ERROR&limit=50
    GET /api/v1/logs?module=ai_service&search=timeout
    GET /api/v1/logs?start_date=2025-11-23&end_date=2025-11-23
    ```

    **Response:**
    ```json
    {
        "entries": [...],
        "total": 150,
        "limit": 100,
        "offset": 0,
        "has_more": true
    }
    ```
    """
    try:
        entries, total = _read_log_entries(
            level=level,
            module=module,
            search=search,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset
        )

        # Convert to LogEntry models
        log_entries = []
        for entry in entries:
            # Extract known fields
            known_fields = {'timestamp', 'level', 'message', 'module', 'logger', 'request_id', 'function', 'line'}
            extra = {k: v for k, v in entry.items() if k not in known_fields}

            log_entries.append(LogEntry(
                timestamp=entry.get('timestamp', ''),
                level=entry.get('level', ''),
                message=entry.get('message', ''),
                module=entry.get('module'),
                logger=entry.get('logger'),
                request_id=entry.get('request_id'),
                function=entry.get('function'),
                line=entry.get('line'),
                extra=extra if extra else None
            ))

        return LogsResponse(
            entries=log_entries,
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total
        )

    except Exception as e:
        logger.error(f"Error querying logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query logs"
        )


@router.get("/download")
async def download_logs(
    date_str: Optional[str] = Query(
        None,
        alias="date",
        description="Date to download logs for (YYYY-MM-DD). If not provided, downloads current log."
    ),
    log_type: str = Query(
        "app",
        description="Log type to download: 'app' (all logs) or 'error' (errors only)"
    )
):
    """
    Download log file for a specific date.

    Downloads the log file as a text file attachment.

    **Parameters:**
    - `date`: Date in YYYY-MM-DD format (optional, defaults to current log)
    - `log_type`: 'app' for all logs, 'error' for error logs only

    **Example:**
    ```
    GET /api/v1/logs/download?date=2025-11-23
    GET /api/v1/logs/download?log_type=error
    ```
    """
    # Determine log file to download
    if log_type == "error":
        log_filename = "error.log"
    else:
        log_filename = "app.log"

    log_file = os.path.join(LOG_DIR, log_filename)

    # Check if log file exists
    if not os.path.exists(log_file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log file not found: {log_filename}"
        )

    # Generate download filename with date
    download_date = date_str or datetime.now().strftime("%Y-%m-%d")
    download_filename = f"logs-{log_type}-{download_date}.log"

    logger.info(
        "Log file download requested",
        extra={
            "event_type": "log_download",
            "log_type": log_type,
            "date": download_date
        }
    )

    return FileResponse(
        path=log_file,
        filename=download_filename,
        media_type="text/plain"
    )


@router.get("/files", response_model=LogFilesResponse)
async def list_log_files():
    """
    List available log files.

    Returns a list of log files in the logs directory.

    **Response:**
    ```json
    {
        "files": ["app.log", "app.log.1", "error.log"],
        "directory": "/backend/data/logs"
    }
    ```
    """
    try:
        if not os.path.exists(LOG_DIR):
            return LogFilesResponse(files=[], directory=LOG_DIR)

        files = [
            f for f in os.listdir(LOG_DIR)
            if f.endswith('.log') or '.log.' in f
        ]
        files.sort()

        return LogFilesResponse(
            files=files,
            directory=LOG_DIR
        )

    except Exception as e:
        logger.error(f"Error listing log files: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list log files"
        )
