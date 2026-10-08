---
sidebar_position: 5
---

# Entities

Entities represent recurring subjects detected across your cameras - people, vehicles, and other recognizable objects. ArgusAI automatically identifies and tracks these subjects over time.

## Understanding Entities

### What Are Entities?

Entities are persistent records of subjects that appear in multiple events:

- **People**: Regular visitors, family members, delivery personnel
- **Vehicles**: Your car, neighbor's vehicles, delivery trucks
- **Other**: Future support for pets, packages, etc.

### How Entities Work

1. AI analyzes an event and extracts subject details
2. System checks for matching existing entities
3. If match found, event is linked to that entity
4. If no match, a new entity may be created
5. Entity history grows with each linked event

### Entity Attributes

| Attribute | Description | Example |
|-----------|-------------|---------|
| **Type** | Entity category | Person, Vehicle |
| **Name** | Display name (if set) | "White Toyota Camry" |
| **First Seen** | When first detected | Dec 20, 2025 |
| **Last Seen** | Most recent appearance | Dec 25, 2025 |
| **Event Count** | Number of linked events | 42 |

#### Vehicle-Specific Attributes

| Attribute | Description | Example |
|-----------|-------------|---------|
| **Color** | Vehicle color | White, Black, Silver |
| **Make** | Manufacturer | Toyota, Ford, Tesla |
| **Model** | Vehicle model | Camry, F-150, Model 3 |

## Browsing Entities

### Entity List

The main Entities page shows all recognized entities:

- **Thumbnail**: Representative image
- **Name**: Entity identifier
- **Type Badge**: Person or Vehicle
- **Event Count**: Number of appearances
- **Last Seen**: Most recent timestamp

### Filtering

Filter entities using:

| Filter | Options |
|--------|---------|
| **Type** | All, Person, Vehicle |
| **Sort By** | Last Seen, First Seen, Event Count, Name |
| **Search** | Text search in entity names |

### Entity Cards

Each entity card shows:

- Primary thumbnail from recent event
- Entity name or auto-generated label
- Type indicator (person/vehicle icon)
- Quick stats (events, last seen)

## Entity Details

### Viewing an Entity

Click any entity to see full details:

#### Overview Section
- Large representative image
- Entity name and type
- All extracted attributes
- First and last seen dates
- Total event count

#### Timeline Section
- Chronological list of all linked events
- Event thumbnails and timestamps
- Camera location for each appearance
- Click events to view details

#### Activity Pattern
- Visual representation of when entity appears
- Time-of-day distribution
- Day-of-week patterns
- Helps identify regular visitors

### Editing Entity Details

Customize entity information:

1. Click **Edit** on the entity detail page
2. Modify:
   - **Name**: Give a friendly name
   - **Notes**: Add personal notes
3. Click **Save**

## Managing Event Links

### Why Manage Links?

AI matching isn't perfect. You may need to:

- Remove incorrectly linked events
- Add events that should be linked
- Merge duplicate entities

### Unlinking Events

Remove an event from an entity:

1. Open the entity detail page
2. Find the incorrect event in the timeline
3. Click the **Unlink** (X) button
4. Event is removed from entity

The event remains in the system, just unlinked from this entity.

### Linking Events

Add an unlinked event to an entity:

1. Open the event you want to link
2. Click **Add to Entity**
3. Search for the correct entity
4. Select the entity from results
5. Event is linked immediately

### Merging Entities

Combine duplicate entities:

1. Go to the Entities page
2. Select entities to merge (checkboxes)
3. Click **Merge Selected**
4. Choose which entity to keep as primary
5. Confirm the merge

After merging:
- All events from both entities are combined
- The non-primary entity is deleted
- Attributes are merged (primary takes precedence)

:::caution
Entity merges cannot be undone. Review carefully before confirming.
:::

## Entity Alerts

Create notifications for specific entities:

1. Open entity detail page
2. Click **Create Alert Rule**
3. Configure notification settings:
   - **Notification Type**: Push, Webhook
   - **Schedule**: When to alert
   - **Cooldown**: Minimum time between alerts
4. Save the rule

Now you'll be notified when that specific entity is detected.

### Alert Use Cases

- Know when your car leaves/returns
- Track when a specific delivery person arrives
- Monitor for unfamiliar vehicles
- Get notified of repeat visitors

## Learning from Corrections

ArgusAI learns from your manual corrections:

### How Learning Works

| Action | What System Learns |
|--------|-------------------|
| **Unlink event** | These features don't match this entity |
| **Link event** | These features do match this entity |
| **Merge entities** | These variations represent the same subject |

### Reference Galleries

Named people and vehicles are recognized from small **reference crops**, not
from whole camera frames:

- **People**: face crops (OpenCV YuNet detector + SFace recognizer, run
  locally). A person is named only when a face in the snapshot matches one of
  their reference faces closely enough, and clearly better than anyone else's.
- **Vehicles**: vehicle crops from the detector, compared with the vehicle's
  reference crops, plus the crop's colour and the make in the AI description.
  A vehicle with references needs its crop to agree; a car that only sits
  parked in the frame is not linked to every passing van.

References are added only when **you** confirm them:

1. **Assigning an event** to a person or vehicle adds that event's face or
   vehicle crop to its references. If the event shows several similar
   vehicles, nothing is added and the response lists the crops so you can
   pick one.
2. **Use as reference** (`POST /api/v1/context/entities/{id}/gallery` with an
   `event_id` and optional `observation_id`) adds a specific crop without
   changing the event's links.
3. **Unlinking** an event removes the references it contributed. Automatic
   matches never add references, so a wrong match can't spread.

For good results, assign 3 to 5 clear events per entity, including a night
one. `GET /api/v1/context/entities/{id}/gallery` lists the references; an
admin can clear them with `DELETE /api/v1/context/entities/{id}/gallery`.
Face and vehicle analysis follow the **Face recognition** and **Vehicle
recognition** privacy settings.

### Optional ArcFace face model

Faces are matched with SFace by default (Apache-2.0, downloaded with the
other models). ArcFace (InsightFace `w600k_r50`) is a stronger identity
model you can switch to, but its weights are licensed by InsightFace for
**non-commercial research use only**. ArgusAI therefore never ships or
downloads them: you get them yourself and decide whether that licence fits
your use.

1. Download InsightFace's `buffalo_l` model pack from the InsightFace
   project and take `w600k_r50.onnx` out of it.
2. Put it at `backend/app/models/arcface/w600k_r50.onnx` (ignored by git), or
   anywhere else and set `ARGUS_ARCFACE_MODEL_PATH` to the file.
3. Check it: `python scripts/verify_arcface_weights.py --load`. The file must
   have SHA-256
   `4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43`
   (the `buffalo_l` release). For a different export, set
   `ARGUS_ARCFACE_SHA256` to its hash. You can also check by hand with
   `shasum -a 256 w600k_r50.onnx` (macOS) or `sha256sum w600k_r50.onnx`.
4. Set `ARGUS_FACE_RECOGNIZER=arcface` in `backend/.env` and restart the
   backend. If the file is missing or the checksum does not match, ArgusAI
   logs a warning and keeps using SFace.

**Re-enroll after switching.** Face references are kept per model: SFace and
ArcFace vectors are never compared with each other, so right after a switch
no one is recognised. Rebuild the references from the stored face crops
(back up the database first):

```bash
python scripts/reembed_face_gallery.py          # shows what would change
python scripts/reembed_face_gallery.py --apply  # then restart the backend
```

Older references without a stored crop are skipped; assign a few clear
events to those people again. To go back to SFace, remove the setting,
restart, and run the same script again. ArcFace uses its own match
threshold (cosine 0.36). The `ARGUS_FACE_MATCH_THRESHOLD` process environment
variable overrides it; set it in the service environment, not in `backend/.env`.

### Improving Accuracy

To improve entity matching over time:

1. Regularly review recent entity assignments
2. Correct any obvious mistakes
3. Merge duplicate entities promptly
4. Provide clear entity names

## Tips

### Naming Entities

Good names help you identify entities quickly:

| Type | Good Names | Avoid |
|------|------------|-------|
| Vehicles | "White Toyota Camry", "Amazon Van" | "Car 1", "Unknown" |
| People | "Mail Carrier", "Neighbor John" | "Person", "Unknown Person" |

### Keeping Entities Clean

- Review entities monthly
- Merge obvious duplicates
- Delete obsolete entities
- Archive entities for subjects that no longer appear

### Privacy Considerations

- Entity data, including face and vehicle crops, is stored locally
- Face recognition runs only when **Face recognition** is enabled in privacy
  settings; deleting all face data also removes face references
- Vehicle matching uses vehicle crops, colour, and make/model
- You control all entity data
