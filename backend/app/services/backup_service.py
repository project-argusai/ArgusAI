"""
Backup and Restore Service (Story 6.4)

This module implements system backup and restore functionality:
- Create full system backups (database, thumbnails, settings)
- Restore from backup archives
- List available backups
- Automatic backup scheduling support
- Backup retention management

Features:
    - ZIP archive creation with database, thumbnails, settings
    - Metadata tracking (timestamp, version, file counts)
    - Validation before restore (ZIP integrity, version check)
    - Safe restore with pre-restore backup
    - Disk space checking before operations

Usage:
    backup_service = get_backup_service()
    result = await backup_service.create_backup()
    # result.download_url contains the download path
"""
import os
import json
import shutil
import zipfile
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)

# Application version for backup compatibility
APP_VERSION = "1.0.0"


@dataclass
class BackupResult:
    """Result of a backup operation"""
    success: bool
    timestamp: str
    size_bytes: int
    download_url: str
    message: str
    database_size_bytes: int = 0
    thumbnails_count: int = 0
    thumbnails_size_bytes: int = 0
    settings_count: int = 0


@dataclass
class RestoreResult:
    """Result of a restore operation"""
    success: bool
    message: str
    events_restored: int = 0
    settings_restored: int = 0
    thumbnails_restored: int = 0
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class BackupInfo:
    """Information about an available backup"""
    timestamp: str
    size_bytes: int
    created_at: str
    app_version: str
    database_size_bytes: int = 0
    thumbnails_count: int = 0
    download_url: str = ""


@dataclass
class BackupContents:
    """Information about what's contained in a backup (FF-007)"""
    has_database: bool = False
    has_thumbnails: bool = False
    has_settings: bool = False
    database_size_bytes: int = 0
    thumbnails_count: int = 0
    settings_count: int = 0


@dataclass
class ValidationResult:
    """Result of backup validation"""
    valid: bool
    message: str
    app_version: Optional[str] = None
    backup_timestamp: Optional[str] = None
    warnings: List[str] = None
    contents: Optional[BackupContents] = None  # FF-007: What's in the backup

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class BackupService:
    """
    Service for system backup and restore operations

    Handles:
        - Full system backup creation (database, thumbnails, settings)
        - Backup archive management
        - System restore from backup
        - Backup validation
        - Retention policy for old backups
    """

    # Required files in a valid backup ZIP
    REQUIRED_FILES = ["database.db", "metadata.json"]
    OPTIONAL_FILES = ["settings.json", "thumbnails/"]

    def __init__(self, session_factory=None):
        """
        Initialize BackupService

        Args:
            session_factory: Optional SQLAlchemy session factory (for testing).
                           Defaults to SessionLocal from app.core.database.
        """
        self.session_factory = session_factory or SessionLocal

        # Calculate paths relative to backend directory
        self.backend_dir = Path(__file__).parent.parent.parent
        self.data_dir = self.backend_dir / "data"
        self.backup_dir = self.data_dir / "backups"
        self.database_path = self.data_dir / "app.db"
        self.thumbnails_dir = self.data_dir / "thumbnails"

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "BackupService initialized",
            extra={
                "backup_dir": str(self.backup_dir),
                "database_path": str(self.database_path),
                "thumbnails_dir": str(self.thumbnails_dir)
            }
        )

    async def create_backup(
        self,
        include_database: bool = True,
        include_thumbnails: bool = True,
        include_settings: bool = True
    ) -> BackupResult:
        """
        Create a system backup with selective components (FF-007)

        Creates a ZIP archive containing selected components:
        - database.db: SQLite database copy (if include_database=True)
        - metadata.json: Backup metadata (timestamp, version, counts)
        - settings.json: System settings export (if include_settings=True)
        - thumbnails/: All event thumbnail images (if include_thumbnails=True)

        Args:
            include_database: Include events, cameras, alert rules (default True)
            include_thumbnails: Include thumbnail images (default True)
            include_settings: Include system settings (default True)

        Returns:
            BackupResult with backup details and download URL

        Raises:
            Exception: If backup creation fails
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
        temp_dir = self.backup_dir / f"backup-{timestamp}"
        zip_path = self.backup_dir / f"backup-{timestamp}.zip"

        logger.info(
            "Starting backup creation",
            extra={
                "timestamp": timestamp,
                "temp_dir": str(temp_dir),
                "include_database": include_database,
                "include_thumbnails": include_thumbnails,
                "include_settings": include_settings
            }
        )

        try:
            # Check disk space
            disk_usage = shutil.disk_usage(self.backup_dir)
            estimated_size = self._estimate_backup_size(include_database, include_thumbnails)

            if disk_usage.free < estimated_size * 2:  # Need 2x for temp + zip
                return BackupResult(
                    success=False,
                    timestamp=timestamp,
                    size_bytes=0,
                    download_url="",
                    message=f"Insufficient disk space. Need {estimated_size * 2 // (1024*1024)} MB, have {disk_usage.free // (1024*1024)} MB"
                )

            # Create temp directory
            temp_dir.mkdir(parents=True, exist_ok=True)

            # 1. Copy database (if selected)
            db_size = 0
            if include_database:
                db_size = self._copy_database(temp_dir)

            # 2. Copy thumbnails (if selected)
            thumb_count, thumb_size = 0, 0
            if include_thumbnails:
                thumb_count, thumb_size = self._copy_thumbnails(temp_dir)

            # 3. Export settings (if selected)
            settings_count = 0
            if include_settings:
                settings_count = self._export_settings(temp_dir)

            # 4. Create metadata (always included)
            metadata = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "app_version": APP_VERSION,
                "database_size_bytes": db_size,
                "thumbnails_count": thumb_count,
                "thumbnails_size_bytes": thumb_size,
                "settings_count": settings_count,
                "includes": {
                    "database": include_database,
                    "thumbnails": include_thumbnails,
                    "settings": include_settings
                }
            }

            with open(temp_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)

            # 5. Create ZIP archive
            zip_size = self._create_zip_archive(temp_dir, zip_path)

            # 6. Cleanup temp directory
            shutil.rmtree(temp_dir)

            download_url = f"/api/v1/system/backup/{timestamp}/download"

            logger.info(
                "Backup created successfully",
                extra={
                    "timestamp": timestamp,
                    "size_bytes": zip_size,
                    "database_size": db_size,
                    "thumbnails_count": thumb_count,
                    "settings_count": settings_count
                }
            )

            return BackupResult(
                success=True,
                timestamp=timestamp,
                size_bytes=zip_size,
                download_url=download_url,
                message="Backup created successfully",
                database_size_bytes=db_size,
                thumbnails_count=thumb_count,
                thumbnails_size_bytes=thumb_size,
                settings_count=settings_count
            )

        except Exception as e:
            logger.error(f"Backup creation failed: {e}", exc_info=True)

            # Cleanup on failure
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            if zip_path.exists():
                zip_path.unlink()

            return BackupResult(
                success=False,
                timestamp=timestamp,
                size_bytes=0,
                download_url="",
                message=f"Backup failed: {str(e)}"
            )

    def _estimate_backup_size(
        self,
        include_database: bool = True,
        include_thumbnails: bool = True
    ) -> int:
        """Estimate total backup size in bytes based on selected components"""
        size = 0

        if include_database and self.database_path.exists():
            size += self.database_path.stat().st_size

        if include_thumbnails and self.thumbnails_dir.exists():
            for f in self.thumbnails_dir.rglob("*"):
                if f.is_file():
                    size += f.stat().st_size

        return size

    def _copy_database(self, temp_dir: Path) -> int:
        """
        Copy database file to temp directory

        Uses shutil.copy2 to preserve metadata.
        For a production system, could use VACUUM INTO for consistency.

        Returns:
            Size of copied database in bytes
        """
        if not self.database_path.exists():
            logger.warning("Database file not found, creating empty backup")
            return 0

        dest_path = temp_dir / "database.db"
        shutil.copy2(self.database_path, dest_path)

        size = dest_path.stat().st_size
        logger.debug(f"Database copied: {size} bytes")

        return size

    def _copy_thumbnails(self, temp_dir: Path) -> tuple[int, int]:
        """
        Copy thumbnails directory to temp directory

        Returns:
            Tuple of (file_count, total_size_bytes)
        """
        if not self.thumbnails_dir.exists():
            logger.debug("No thumbnails directory to backup")
            return 0, 0

        dest_thumbnails = temp_dir / "thumbnails"
        file_count = 0
        total_size = 0

        try:
            # Use copytree with dirs_exist_ok for recursive copy
            shutil.copytree(
                self.thumbnails_dir,
                dest_thumbnails,
                dirs_exist_ok=True
            )

            # Count files and size
            for f in dest_thumbnails.rglob("*"):
                if f.is_file():
                    file_count += 1
                    total_size += f.stat().st_size

            logger.debug(f"Thumbnails copied: {file_count} files, {total_size} bytes")

        except Exception as e:
            logger.warning(f"Error copying thumbnails: {e}")

        return file_count, total_size

    def _export_settings(self, temp_dir: Path) -> int:
        """
        Export system settings to JSON file

        Returns:
            Number of settings exported
        """
        db = self.session_factory()
        try:
            settings = db.query(SystemSetting).all()

            settings_data = {}
            for setting in settings:
                # Don't export encrypted values - they need to be re-entered
                if setting.value.startswith("encrypted:"):
                    settings_data[setting.key] = "[ENCRYPTED - Re-enter after restore]"
                else:
                    settings_data[setting.key] = setting.value

            with open(temp_dir / "settings.json", "w") as f:
                json.dump(settings_data, f, indent=2)

            logger.debug(f"Settings exported: {len(settings)} entries")
            return len(settings)

        except Exception as e:
            logger.warning(f"Error exporting settings: {e}")
            return 0
        finally:
            db.close()

    def _create_zip_archive(self, source_dir: Path, zip_path: Path) -> int:
        """
        Create ZIP archive from source directory

        Returns:
            Size of created ZIP file in bytes
        """
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(source_dir)
                    zf.write(file_path, arcname)

        return zip_path.stat().st_size

    def get_backup_path(self, timestamp: str) -> Optional[Path]:
        """
        Get path to backup ZIP file by timestamp

        Returns:
            Path to backup file if exists, None otherwise
        """
        zip_path = self.backup_dir / f"backup-{timestamp}.zip"
        if zip_path.exists():
            return zip_path
        return None

    def validate_backup(self, zip_path: Path) -> ValidationResult:
        """
        Validate a backup ZIP file

        Checks:
        - ZIP file integrity
        - Required files present
        - Metadata format and version

        Returns:
            ValidationResult with validation status
        """
        warnings = []

        # Check if valid ZIP
        if not zipfile.is_zipfile(zip_path):
            return ValidationResult(
                valid=False,
                message="File is not a valid ZIP archive"
            )

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Test ZIP integrity
                bad_file = zf.testzip()
                if bad_file:
                    return ValidationResult(
                        valid=False,
                        message=f"ZIP archive is corrupted: {bad_file}"
                    )

                # Check required files
                file_list = zf.namelist()
                for required in self.REQUIRED_FILES:
                    if required not in file_list:
                        return ValidationResult(
                            valid=False,
                            message=f"Missing required file: {required}"
                        )

                # Read and validate metadata
                with zf.open("metadata.json") as mf:
                    metadata = json.load(mf)

                backup_version = metadata.get("app_version", "unknown")
                backup_timestamp = metadata.get("timestamp", "unknown")

                # Version compatibility check
                if backup_version != APP_VERSION:
                    warnings.append(
                        f"Backup from version {backup_version}, current version is {APP_VERSION}. "
                        "Some features may not work correctly."
                    )

                # FF-007: Determine what's in the backup
                includes = metadata.get("includes", {})
                # Check file list for backwards compatibility with old backups
                has_database = "database.db" in file_list
                has_thumbnails = any(f.startswith("thumbnails/") for f in file_list)
                has_settings = "settings.json" in file_list

                # Override with metadata includes if present (new format)
                if includes:
                    has_database = includes.get("database", has_database)
                    has_thumbnails = includes.get("thumbnails", has_thumbnails)
                    has_settings = includes.get("settings", has_settings)

                contents = BackupContents(
                    has_database=has_database,
                    has_thumbnails=has_thumbnails,
                    has_settings=has_settings,
                    database_size_bytes=metadata.get("database_size_bytes", 0),
                    thumbnails_count=metadata.get("thumbnails_count", 0),
                    settings_count=metadata.get("settings_count", 0)
                )

                return ValidationResult(
                    valid=True,
                    message="Backup is valid",
                    app_version=backup_version,
                    backup_timestamp=backup_timestamp,
                    warnings=warnings,
                    contents=contents
                )

        except json.JSONDecodeError:
            return ValidationResult(
                valid=False,
                message="Invalid metadata.json format"
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                message=f"Validation error: {str(e)}"
            )

    async def restore_from_backup(
        self,
        zip_path: Path,
        stop_tasks_callback=None,
        start_tasks_callback=None,
        restore_database: bool = True,
        restore_thumbnails: bool = True,
        restore_settings: bool = True
    ) -> RestoreResult:
        """
        Restore system from backup ZIP with selective components (FF-007)

        Process:
        1. Validate ZIP structure
        2. Stop background tasks
        3. Backup current database (if restoring database)
        4. Extract and replace selected files
        5. Restart background tasks

        Args:
            zip_path: Path to backup ZIP file
            stop_tasks_callback: Async function to stop background tasks
            start_tasks_callback: Async function to restart background tasks
            restore_database: Restore events, cameras, alert rules (default True)
            restore_thumbnails: Restore thumbnail images (default True)
            restore_settings: Restore system settings (default True)

        Returns:
            RestoreResult with restore status
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
        temp_dir = self.backup_dir / f"restore-{timestamp}"
        warnings = []

        logger.info(
            "Starting restore from backup",
            extra={
                "zip_path": str(zip_path),
                "timestamp": timestamp,
                "restore_database": restore_database,
                "restore_thumbnails": restore_thumbnails,
                "restore_settings": restore_settings
            }
        )

        try:
            # 1. Validate backup
            validation = self.validate_backup(zip_path)
            if not validation.valid:
                return RestoreResult(
                    success=False,
                    message=f"Backup validation failed: {validation.message}"
                )

            if validation.warnings:
                warnings.extend(validation.warnings)

            # FF-007: Check if requested components exist in backup
            if validation.contents:
                if restore_database and not validation.contents.has_database:
                    warnings.append("Database not included in this backup, skipping")
                    restore_database = False
                if restore_thumbnails and not validation.contents.has_thumbnails:
                    warnings.append("Thumbnails not included in this backup, skipping")
                    restore_thumbnails = False
                if restore_settings and not validation.contents.has_settings:
                    warnings.append("Settings not included in this backup, skipping")
                    restore_settings = False

            # 2. Stop background tasks
            if stop_tasks_callback:
                logger.info("Stopping background tasks for restore")
                await stop_tasks_callback()

            try:
                # 3. Backup current database (if restoring database)
                if restore_database and self.database_path.exists():
                    backup_db_path = self.data_dir / f"app.db.backup-{timestamp}"
                    shutil.copy2(self.database_path, backup_db_path)
                    logger.info(f"Current database backed up to {backup_db_path}")

                # 4. Extract ZIP to temp directory
                temp_dir.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(temp_dir)

                # 5. Replace database (if selected)
                events_restored = 0
                if restore_database and (temp_dir / "database.db").exists():
                    shutil.copy2(temp_dir / "database.db", self.database_path)
                    logger.info("Database restored from backup")

                    # Count events in restored database
                    db = self.session_factory()
                    try:
                        from app.models.event import Event
                        events_restored = db.query(Event).count()
                    finally:
                        db.close()

                # 6. Replace thumbnails (if selected)
                thumbnails_restored = 0
                if restore_thumbnails and (temp_dir / "thumbnails").exists():
                    # Clear existing thumbnails
                    if self.thumbnails_dir.exists():
                        shutil.rmtree(self.thumbnails_dir)

                    # Copy from backup
                    shutil.copytree(temp_dir / "thumbnails", self.thumbnails_dir)

                    # Count restored files
                    for f in self.thumbnails_dir.rglob("*"):
                        if f.is_file():
                            thumbnails_restored += 1

                    logger.info(f"Thumbnails restored: {thumbnails_restored} files")

                # 7. Import settings (if selected, non-encrypted only)
                settings_restored = 0
                if restore_settings and (temp_dir / "settings.json").exists():
                    settings_restored = self._import_settings(temp_dir / "settings.json")

                # 8. Cleanup temp directory
                shutil.rmtree(temp_dir)

                logger.info(
                    "Restore completed successfully",
                    extra={
                        "events_restored": events_restored,
                        "thumbnails_restored": thumbnails_restored,
                        "settings_restored": settings_restored
                    }
                )

                return RestoreResult(
                    success=True,
                    message="Restore completed successfully",
                    events_restored=events_restored,
                    settings_restored=settings_restored,
                    thumbnails_restored=thumbnails_restored,
                    warnings=warnings
                )

            finally:
                # 9. Restart background tasks
                if start_tasks_callback:
                    logger.info("Restarting background tasks after restore")
                    await start_tasks_callback()

        except Exception as e:
            logger.error(f"Restore failed: {e}", exc_info=True)

            # Cleanup temp directory on failure
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

            return RestoreResult(
                success=False,
                message=f"Restore failed: {str(e)}",
                warnings=warnings
            )

    def _import_settings(self, settings_path: Path) -> int:
        """
        Import settings from JSON file

        Skips encrypted values (they show placeholder text)

        Returns:
            Number of settings imported
        """
        db = self.session_factory()
        imported = 0

        try:
            with open(settings_path, "r") as f:
                settings_data = json.load(f)

            for key, value in settings_data.items():
                # Skip placeholder for encrypted values
                if value == "[ENCRYPTED - Re-enter after restore]":
                    continue

                setting = db.query(SystemSetting).filter(
                    SystemSetting.key == key
                ).first()

                if setting:
                    setting.value = value
                else:
                    setting = SystemSetting(key=key, value=value)
                    db.add(setting)

                imported += 1

            db.commit()
            logger.debug(f"Settings imported: {imported} entries")

        except Exception as e:
            logger.warning(f"Error importing settings: {e}")
            db.rollback()
        finally:
            db.close()

        return imported

    def list_backups(self) -> List[BackupInfo]:
        """
        List all available backups

        Returns:
            List of BackupInfo objects sorted by timestamp (newest first)
        """
        backups = []

        if not self.backup_dir.exists():
            return backups

        for zip_file in self.backup_dir.glob("backup-*.zip"):
            try:
                # Extract timestamp from filename
                timestamp = zip_file.stem.replace("backup-", "")
                size = zip_file.stat().st_size
                created_at = datetime.fromtimestamp(
                    zip_file.stat().st_mtime,
                    tz=timezone.utc
                ).isoformat()

                # Try to read metadata from ZIP
                app_version = APP_VERSION
                db_size = 0
                thumb_count = 0

                try:
                    with zipfile.ZipFile(zip_file, "r") as zf:
                        if "metadata.json" in zf.namelist():
                            with zf.open("metadata.json") as mf:
                                metadata = json.load(mf)
                                app_version = metadata.get("app_version", APP_VERSION)
                                db_size = metadata.get("database_size_bytes", 0)
                                thumb_count = metadata.get("thumbnails_count", 0)
                except:
                    pass

                backups.append(BackupInfo(
                    timestamp=timestamp,
                    size_bytes=size,
                    created_at=created_at,
                    app_version=app_version,
                    database_size_bytes=db_size,
                    thumbnails_count=thumb_count,
                    download_url=f"/api/v1/system/backup/{timestamp}/download"
                ))

            except Exception as e:
                logger.warning(f"Error reading backup info for {zip_file}: {e}")

        # Sort by timestamp (newest first)
        backups.sort(key=lambda b: b.timestamp, reverse=True)

        return backups

    def delete_backup(self, timestamp: str) -> bool:
        """
        Delete a backup by timestamp

        Returns:
            True if deleted, False if not found
        """
        zip_path = self.backup_dir / f"backup-{timestamp}.zip"

        if zip_path.exists():
            zip_path.unlink()
            logger.info(f"Backup deleted: {timestamp}")
            return True

        return False

    def cleanup_old_backups(self, keep_count: int = 7) -> int:
        """
        Remove old backups, keeping only the most recent ones

        Args:
            keep_count: Number of backups to retain

        Returns:
            Number of backups deleted
        """
        backups = self.list_backups()

        if len(backups) <= keep_count:
            return 0

        deleted = 0
        for backup in backups[keep_count:]:
            if self.delete_backup(backup.timestamp):
                deleted += 1

        logger.info(
            f"Backup cleanup complete: {deleted} old backups deleted",
            extra={"kept": keep_count, "deleted": deleted}
        )

        return deleted


# Global instance
_backup_service: Optional[BackupService] = None


def get_backup_service() -> BackupService:
    """
    Get the global BackupService instance

    Returns:
        BackupService instance
    """
    global _backup_service

    if _backup_service is None:
        _backup_service = BackupService()

    return _backup_service
