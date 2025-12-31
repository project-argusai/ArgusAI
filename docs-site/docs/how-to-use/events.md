---
sidebar_position: 3
---

# Events

The Events page displays a chronological timeline of all detected activity from your cameras. This is where you'll spend most of your time reviewing what's happening around your home.

## Events Timeline

### Timeline Layout

Events are displayed in a scrollable timeline:

- **Newest events** appear at the top
- **Infinite scroll** loads more events as you scroll down
- **Real-time updates** add new events automatically

### Event Cards

Each event displays:

| Element | Description |
|---------|-------------|
| **Thumbnail** | Snapshot image from the event |
| **Description** | AI-generated text describing the activity |
| **Camera** | Which camera captured the event |
| **Timestamp** | When the event occurred |
| **Detection Badge** | Type of detection (person, vehicle, etc.) |
| **Confidence** | AI confidence score as percentage |

### Doorbell Events

Doorbell ring events have a distinct appearance:

- Bell icon indicator
- "Doorbell Ring" label
- Same event details as other events

### Video Playback

Events from UniFi Protect cameras can include full motion video clips (when video storage is enabled in Settings):

| Element | Description |
|---------|-------------|
| **Video Icon** | Blue video icon appears on events with stored video |
| **Play** | Click the icon to open the video player modal |
| **Download** | Download button to save the video file locally |

#### Video Player Controls

The video player modal provides:

- **Play/Pause**: Start or stop video playback
- **Mute/Unmute**: Toggle audio on/off
- **Fullscreen**: Expand video to full screen
- **Download**: Save the video as an MP4 file

:::tip
Enable **Store Motion Videos** in Settings > General tab to capture video clips from your Protect cameras.
:::

## Filtering Events

### Filter Panel

Use the filter sidebar to narrow down events:

#### Search
- Full-text search in event descriptions
- Finds events mentioning specific terms
- Example: "delivery" or "red car"

#### Camera Filter
- Select specific cameras
- Choose one or multiple cameras
- "All Cameras" shows everything

#### Date Range
- Set start and end dates
- Quick presets: Today, Yesterday, Last 7 Days, Last 30 Days
- Custom date picker for specific ranges

#### Detection Type
Filter by what was detected:
- **Person**: Human activity
- **Vehicle**: Cars, trucks, motorcycles
- **Package**: Delivery boxes
- **Animal**: Pets and wildlife
- **Ring**: Doorbell events

#### Source Type
Filter by camera type:
- **Protect**: UniFi Protect cameras
- **RTSP**: Generic IP cameras
- **USB**: Webcams

#### Confidence Level
Set minimum confidence threshold:
- Slider from 0-100%
- Higher values show more certain detections
- Useful for filtering out false positives

#### Analysis Mode
Filter by how the event was analyzed:
- **Single Frame**: Snapshot analysis
- **Multi-Frame**: Multiple frame analysis
- **Video Native**: Full video analysis

### Clearing Filters

- Click **Clear All** to reset all filters
- Click the X on individual filter chips
- Filters persist in the URL for bookmarking

## Viewing Event Details

### Opening Events

Click any event card to open the detail view:

- **Full-size image** with zoom capability
- **Complete description** from AI analysis
- **Metadata** (camera, time, confidence)
- **Frame gallery** for multi-frame events

### Detail View Features

#### Image Navigation
- Click to zoom in/out
- Swipe or use arrows for multi-frame events
- Download original image

#### Event Metadata
- Source camera with link to camera page
- Exact timestamp with timezone
- Detection type and confidence
- Analysis mode used

#### Entity Information
- Linked entities (if any)
- Option to assign to existing entity
- Create new entity from event

### Keyboard Navigation

In the detail view:
- **Left/Right arrows**: Navigate between events
- **Escape**: Close detail view
- **R**: Re-analyze event
- **D**: Download image

## Event Actions

### Re-Analyze

If an event description is poor or outdated:

1. Open the event detail view
2. Click **Re-analyse**
3. Wait for new AI analysis
4. Compare with previous description

Re-analysis uses your current AI settings and provider configuration.

### Providing Feedback

Rate AI descriptions to improve quality:

1. Open event details
2. Click **thumbs up** or **thumbs down**
3. Optionally add a comment
4. Feedback helps improve future analysis

### Bulk Actions

#### Multi-Select Mode

1. Click **Select** button in the header
2. Check individual events or **Select All**
3. Selected events show checkmarks

#### Bulk Delete

With events selected:

1. Click **Delete** in the floating action bar
2. Confirm deletion in the dialog
3. Events and their media are permanently removed

:::caution
Deleted events cannot be recovered. Consider exporting important events first.
:::

## Real-Time Updates

### New Event Indicator

When new events arrive:

- **Badge** shows count of new events
- **Toast notification** appears briefly
- Click **Refresh** to load new events

### WebSocket Connection

Events page maintains a live connection:

- Instant notification of new events
- No manual refresh required
- Connection status shown in header

## Tips

### Finding Specific Events

- Use search for descriptions ("person with package")
- Filter by camera for location-specific activity
- Set date range for historical review
- Combine filters for precise results

### Managing Large Event Volumes

- Set higher confidence thresholds
- Filter to specific cameras
- Use date ranges to limit scope
- Consider adjusting camera sensitivity

### Bookmarking Searches

Filter parameters are stored in the URL:
- Bookmark filtered views for quick access
- Share specific searches with others
- Browser back/forward navigates filter history
