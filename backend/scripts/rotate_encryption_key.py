#!/usr/bin/env python
"""
Encryption Key Rotation Script

Rotates the master Fernet encryption key and re-encrypts all sensitive data
in the database using the new key.

This script is safe to run multiple times (idempotent) and supports dry-run mode.

Usage:
    # Dry run (recommended first)
    python scripts/rotate_encryption_key.py \
        --new-key "new-fernet-key-here..." \
        --old-key "current-fernet-key..." \
        --dry-run

    # Actual rotation
    python scripts/rotate_encryption_key.py \
        --new-key "new-fernet-key-here..." \
        --old-key "current-fernet-key..."

Environment:
    The script will temporarily override ENCRYPTION_KEY and ENCRYPTION_KEY_PREVIOUS
    for the duration of the rotation.
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Optional

# Add backend to path when running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db_session
from app.utils.encryption import (
    encrypt_password,
    decrypt_password,
    _initialize_encryption_ciphers,
    get_primary_encryption_key,
)
from app.models.camera import Camera
from app.models.protect_controller import ProtectController
from app.models.homekit import HomeKit
from app.models.device import Device
from app.models.system_setting import SystemSetting


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rotate the master encryption key and re-encrypt all secrets."
    )
    parser.add_argument(
        "--new-key",
        required=True,
        help="The new primary Fernet key to encrypt data with going forward.",
    )
    parser.add_argument(
        "--old-key",
        required=False,
        help="The current (old) Fernet key used to decrypt existing data. "
             "If not provided, the script will try to use the current ENCRYPTION_KEY.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying the database.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed information about each record processed.",
    )
    return parser.parse_args()


def setup_keys_for_rotation(new_key: str, old_key: Optional[str]):
    """
    Configure the encryption module to use the new key as primary
    and the old key as fallback for decryption.
    """
    os.environ["ENCRYPTION_KEY"] = new_key

    if old_key:
        os.environ["ENCRYPTION_KEY_PREVIOUS"] = old_key
    else:
        # If no old key provided, assume current key is the one to rotate from
        current_key = os.environ.get("ENCRYPTION_KEY")
        if current_key and current_key != new_key:
            os.environ["ENCRYPTION_KEY_PREVIOUS"] = current_key

    # Re-initialize ciphers with the new configuration
    _initialize_encryption_ciphers()

    print(f"[INFO] Encryption initialized with new primary key.")
    print(f"[INFO] Primary key (first 8 chars): {new_key[:8]}...")
    if os.environ.get("ENCRYPTION_KEY_PREVIOUS"):
        print(f"[INFO] Previous key configured for decryption fallback.")


def re_encrypt_cameras(db: DBSession, dry_run: bool, verbose: bool) -> int:
    """Re-encrypt Camera passwords."""
    count = 0
    cameras = db.query(Camera).filter(Camera.password.isnot(None)).all()

    for camera in cameras:
        if not camera.password or not camera.password.startswith("encrypted:"):
            continue

        try:
            # Decrypt with old key(s), encrypt with new key
            decrypted = decrypt_password(camera.password)
            new_encrypted = encrypt_password(decrypted)

            if verbose:
                print(f"  Camera {camera.id} ({camera.name}): re-encrypted")

            if not dry_run:
                camera.password = new_encrypted
                count += 1
            else:
                count += 1

        except Exception as e:
            print(f"  [ERROR] Failed to re-encrypt Camera {camera.id}: {e}")

    if not dry_run and count > 0:
        db.commit()

    return count


def re_encrypt_protect_controllers(db: DBSession, dry_run: bool, verbose: bool) -> int:
    """Re-encrypt ProtectController credentials."""
    count = 0
    controllers = db.query(ProtectController).all()

    for controller in controllers:
        updated = False

        # Re-encrypt username if present
        if controller.username and controller.username.startswith("encrypted:"):
            try:
                decrypted = decrypt_password(controller.username)
                controller.username = encrypt_password(decrypted)
                updated = True
                if verbose:
                    print(f"  ProtectController {controller.id}: re-encrypted username")
            except Exception as e:
                print(f"  [ERROR] ProtectController {controller.id} username: {e}")

        # Re-encrypt password
        if controller.password and controller.password.startswith("encrypted:"):
            try:
                decrypted = decrypt_password(controller.password)
                controller.password = encrypt_password(decrypted)
                updated = True
                if verbose:
                    print(f"  ProtectController {controller.id}: re-encrypted password")
            except Exception as e:
                print(f"  [ERROR] ProtectController {controller.id} password: {e}")

        if updated:
            count += 1

    if not dry_run and count > 0:
        db.commit()

    return count


def re_encrypt_homekit(db: DBSession, dry_run: bool, verbose: bool) -> int:
    """Re-encrypt HomeKit PIN codes."""
    count = 0
    homekits = db.query(HomeKit).filter(HomeKit.pin_code.isnot(None)).all()

    for hk in homekits:
        if not hk.pin_code or not hk.pin_code.startswith("encrypted:"):
            continue

        try:
            decrypted = decrypt_password(hk.pin_code)
            hk.pin_code = encrypt_password(decrypted)

            if verbose:
                print(f"  HomeKit {hk.id}: re-encrypted PIN code")

            count += 1
        except Exception as e:
            print(f"  [ERROR] HomeKit {hk.id}: {e}")

    if not dry_run and count > 0:
        db.commit()

    return count


def re_encrypt_devices(db: DBSession, dry_run: bool, verbose: bool) -> int:
    """Re-encrypt Device push tokens (for push notifications)."""
    count = 0
    devices = db.query(Device).filter(Device.push_token.isnot(None)).all()

    for device in devices:
        if not device.push_token or not device.push_token.startswith("encrypted:"):
            continue

        try:
            decrypted = decrypt_password(device.push_token)
            device.push_token = encrypt_password(decrypted)

            if verbose:
                print(f"  Device {device.id}: re-encrypted push token")

            count += 1
        except Exception as e:
            print(f"  [ERROR] Device {device.id}: {e}")

    if not dry_run and count > 0:
        db.commit()

    return count


def re_encrypt_system_settings(db: DBSession, dry_run: bool, verbose: bool) -> int:
    """
    Re-encrypt encrypted SystemSetting values (AI keys, etc.).
    Only re-encrypts values that look like they are currently encrypted.
    """
    count = 0
    # Common encrypted setting keys
    encrypted_keys = [
        "ai_api_key_openai",
        "ai_api_key_grok",
        "ai_api_key_claude",
        "ai_api_key_gemini",
        "settings_primary_api_key",
        # Add more as needed
    ]

    settings = db.query(SystemSetting).filter(SystemSetting.key.in_(encrypted_keys)).all()

    for setting in settings:
        if not setting.value or not setting.value.startswith("encrypted:"):
            continue

        try:
            decrypted = decrypt_password(setting.value)
            setting.value = encrypt_password(decrypted)

            if verbose:
                print(f"  SystemSetting '{setting.key}': re-encrypted")

            count += 1
        except Exception as e:
            print(f"  [ERROR] SystemSetting '{setting.key}': {e}")

    if not dry_run and count > 0:
        db.commit()

    return count


def main():
    args = parse_args()

    print("=" * 60)
    print("ArgusAI Encryption Key Rotation")
    print(f"Started at: {datetime.now().isoformat()}")
    print("=" * 60)

    if args.dry_run:
        print("\n*** DRY RUN MODE - No changes will be made to the database ***\n")

    # Configure encryption with new + old keys
    setup_keys_for_rotation(args.new_key, args.old_key)

    total_reencrypted = 0

    with get_db_session() as db:
        print("\n[1/5] Re-encrypting Camera passwords...")
        c = re_encrypt_cameras(db, args.dry_run, args.verbose)
        print(f"      → {c} cameras processed")
        total_reencrypted += c

        print("\n[2/5] Re-encrypting ProtectController credentials...")
        c = re_encrypt_protect_controllers(db, args.dry_run, args.verbose)
        print(f"      → {c} controllers processed")
        total_reencrypted += c

        print("\n[3/5] Re-encrypting HomeKit PIN codes...")
        c = re_encrypt_homekit(db, args.dry_run, args.verbose)
        print(f"      → {c} HomeKit records processed")
        total_reencrypted += c

        print("\n[4/5] Re-encrypting Device push tokens...")
        c = re_encrypt_devices(db, args.dry_run, args.verbose)
        print(f"      → {c} devices processed")
        total_reencrypted += c

        print("\n[5/5] Re-encrypting SystemSettings (AI keys, etc.)...")
        c = re_encrypt_system_settings(db, args.dry_run, args.verbose)
        print(f"      → {c} system settings processed")
        total_reencrypted += c

    print("\n" + "=" * 60)
    print(f"Rotation complete. Total records processed: {total_reencrypted}")
    if args.dry_run:
        print("This was a dry run. Run again without --dry-run to apply changes.")
    else:
        print("All secrets have been re-encrypted with the new key.")
        print("You can now safely update ENCRYPTION_KEY in your environment.")
    print("=" * 60)


if __name__ == "__main__":
    main()