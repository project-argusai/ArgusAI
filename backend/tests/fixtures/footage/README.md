# Test Footage for Motion Detection Validation

This directory contains curated video footage for testing ArgusAI motion detection accuracy.

## Directory Structure

```
footage/
├── README.md               # This file
├── manifest.yaml           # Ground truth labels for all clips
├── person/                 # Person detection test clips
├── vehicle/                # Vehicle detection test clips
├── animal/                 # Animal detection test clips
├── package/                # Package detection test clips
└── false_positive/         # Clips with no expected detection (false positive testing)
```

## File Naming Convention

Format: `{type}_{description}_{lighting}_{sequence}.mp4`

Examples:
- `person_walk_day_01.mp4` - Person walking, daytime, sequence 1
- `vehicle_car_night_01.mp4` - Car, nighttime/IR, sequence 1
- `animal_dog_dusk_01.mp4` - Dog, dusk lighting, sequence 1
- `false_shadow_day_01.mp4` - Shadow movement (false positive), daytime

### Type Prefixes
- `person_` - Human detection
- `vehicle_` - Car, truck, motorcycle
- `animal_` - Dog, cat, wildlife
- `package_` - Delivery package
- `false_` - False positive scenario (trees, shadows, rain)

### Lighting Suffixes
- `day` - Normal daylight
- `night` - Night/IR camera mode
- `dusk` - Low light/twilight conditions

## Recommended Video Specifications

| Property | Recommended | Notes |
|----------|-------------|-------|
| Format | MP4 (H.264) | Universal compatibility with OpenCV |
| Resolution | 720p or 1080p | Matches typical security cameras |
| Frame Rate | 15-30 FPS | Standard surveillance rates |
| Duration | 5-30 seconds | Balance coverage vs file size |
| Codec | H.264/AVC | Widely supported |
| Audio | Optional | Not used for motion detection |

## Adding New Test Footage

### Step 1: Record or Source Footage

**Ethical/Legal Sources:**
- Self-recorded footage with personal cameras
- Public domain video (Pexels, Pixabay, archive.org)
- Synthetic footage (video editing tools)
- Commercial stock footage with appropriate license

**Do NOT use:**
- Footage without usage rights
- Footage containing identifiable individuals without consent
- Footage from live camera feeds without authorization

### Step 2: Prepare the Clip

1. Trim to relevant portion (5-30 seconds)
2. Convert to MP4/H.264 if needed:
   ```bash
   ffmpeg -i input.avi -c:v libx264 -crf 23 -c:a aac output.mp4
   ```
3. Rename following naming convention
4. Place in appropriate subdirectory

### Step 3: Add Manifest Entry

Add entry to `manifest.yaml`:

```yaml
- filename: person/person_walk_day_02.mp4
  detection_type: person
  expected_objects: 1
  timestamp_ranges:
    - start: 0.0
      end: 8.5
      objects: ["person"]
  lighting: day
  camera_angle: front-door
  notes: "Person walking toward camera, good lighting"
```

### Step 4: Verify

Run the manifest validation test:
```bash
pytest tests/test_fixtures/test_footage_manifest.py -v
```

## Ground Truth Labels (manifest.yaml)

The `manifest.yaml` file contains structured ground truth labels for all clips.

### Schema

```yaml
version: "1.0"
description: "Ground truth labels for motion detection test footage"
clips:
  - filename: string          # Relative path within footage/
    detection_type: string    # person, vehicle, animal, package, false_positive
    expected_objects: integer # Number of objects to detect (0 for false_positive)
    timestamp_ranges:         # When objects appear
      - start: float         # Start time in seconds
        end: float           # End time in seconds
        objects: [string]    # What appears (e.g., ["person", "dog"])
    lighting: string         # day, night, dusk
    camera_angle: string     # front-door, driveway, backyard, etc.
    notes: string            # Additional context or edge cases
```

### Detection Types

| Type | Description | Expected Behavior |
|------|-------------|-------------------|
| `person` | Human figure detection | Should trigger person sensor |
| `vehicle` | Car, truck, etc. | Should trigger vehicle sensor |
| `animal` | Dog, cat, wildlife | Should trigger animal sensor |
| `package` | Delivered package | Should trigger package sensor |
| `false_positive` | Non-detection scenario | Should NOT trigger any sensor |

## Usage in Tests

Load footage programmatically:

```python
import yaml
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "footage"

def load_manifest():
    """Load ground truth manifest."""
    with open(FIXTURES_DIR / "manifest.yaml") as f:
        return yaml.safe_load(f)

def get_clips_by_type(detection_type: str):
    """Get all clips for a specific detection type."""
    manifest = load_manifest()
    return [c for c in manifest["clips"] if c["detection_type"] == detection_type]

def get_clip_path(filename: str) -> Path:
    """Get full path to a clip file."""
    return FIXTURES_DIR / filename
```

## Git LFS Notice

**Important:** Large video files should use Git LFS to avoid bloating the repository.

### Setup Git LFS (one-time)
```bash
git lfs install
git lfs track "*.mp4"
git add .gitattributes
```

### Alternative: External Storage
If Git LFS is not configured, store clips externally and provide:
1. Download script
2. SHA256 checksums
3. Download URLs or instructions

## Target Metrics

Test footage is used to validate these detection accuracy targets:

| Metric | Target | Description |
|--------|--------|-------------|
| Person Detection Rate | >90% | True positives / total persons |
| Vehicle Detection Rate | >85% | True positives / total vehicles |
| Animal Detection Rate | >80% | True positives / total animals |
| Package Detection Rate | >75% | True positives / total packages |
| False Positive Rate | <20% | False triggers / total clips |

## References

- [PRD Phase 5](../../../../../docs/PRD-phase5.md) - FR29, FR30
- [Backlog TD-003](../../../../../docs/backlog.md) - Real Camera Integration Testing
- [Motion Detection Service](../../../app/services/motion_detection_service.py)
