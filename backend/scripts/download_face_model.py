#!/usr/bin/env python3
"""
Download OpenCV DNN Face Detection Model (Story P4-8.1)

This script downloads the pre-trained face detection model files required
for the FaceDetectionService. The model is based on SSD with ResNet-10
backbone, trained on the WIDER FACE dataset.

Model files:
- deploy.prototxt: Network architecture definition (~30KB)
- res10_300x300_ssd_iter_140000.caffemodel: Pre-trained weights (~10MB)

Usage:
    python scripts/download_face_model.py

The files will be downloaded to:
    backend/app/models/opencv_face/
"""
import os
import sys
import urllib.request
from pathlib import Path


# Model download URLs (official OpenCV repositories)
MODEL_URLS = {
    "deploy.prototxt": (
        "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
    ),
    "res10_300x300_ssd_iter_140000.caffemodel": (
        "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/"
        "res10_300x300_ssd_iter_140000.caffemodel"
    ),
}

# Target directory (relative to this script)
SCRIPT_DIR = Path(__file__).parent
TARGET_DIR = SCRIPT_DIR.parent / "app" / "models" / "opencv_face"


def download_file(url: str, target_path: Path) -> bool:
    """Download a file from URL to target path."""
    print(f"Downloading: {target_path.name}")
    print(f"  From: {url}")

    try:
        # Create parent directory if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Download with progress
        def progress_hook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = min(100, downloaded * 100 / total_size)
                sys.stdout.write(f"\r  Progress: {percent:.1f}%")
                sys.stdout.flush()

        urllib.request.urlretrieve(url, str(target_path), reporthook=progress_hook)
        print(f"\n  Saved to: {target_path}")
        return True

    except Exception as e:
        print(f"\n  Error: {e}")
        return False


def verify_models() -> bool:
    """Verify that model files exist and have reasonable sizes."""
    print("\nVerifying model files...")

    all_ok = True
    for filename in MODEL_URLS.keys():
        filepath = TARGET_DIR / filename
        if filepath.exists():
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"  {filename}: {size_mb:.2f} MB")
        else:
            print(f"  {filename}: MISSING")
            all_ok = False

    return all_ok


def main():
    """Download face detection model files."""
    print("=" * 60)
    print("OpenCV DNN Face Detection Model Downloader")
    print("Story P4-8.1: Face Embedding Storage")
    print("=" * 60)

    print(f"\nTarget directory: {TARGET_DIR}")

    # Check if models already exist
    existing = [f for f in MODEL_URLS.keys() if (TARGET_DIR / f).exists()]
    if len(existing) == len(MODEL_URLS):
        print("\nAll model files already exist!")
        if verify_models():
            print("\nModels verified successfully.")
            return 0
        else:
            print("\nModel verification failed. Re-downloading...")

    # Download missing files
    print("\nDownloading model files...")
    success_count = 0

    for filename, url in MODEL_URLS.items():
        target_path = TARGET_DIR / filename

        if target_path.exists():
            print(f"\nSkipping {filename} (already exists)")
            success_count += 1
            continue

        print()
        if download_file(url, target_path):
            success_count += 1

    print()
    print("=" * 60)

    if success_count == len(MODEL_URLS):
        print(f"Successfully downloaded {success_count}/{len(MODEL_URLS)} files!")
        if verify_models():
            print("\nModel verification passed.")
            print("\nFace detection model is ready to use.")
            return 0
        else:
            print("\nModel verification failed!")
            return 1
    else:
        print(f"Only downloaded {success_count}/{len(MODEL_URLS)} files.")
        print("Some downloads failed. Please check your internet connection and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
