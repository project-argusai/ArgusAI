---
sidebar_position: 3
---

# Entity Recognition

ArgusAI can recognize and track recurring visitors, vehicles, and packages.

## What Are Entities?

Entities are recognized subjects that appear across multiple events:

- **People**: Family members, regular visitors, delivery personnel
- **Vehicles**: Your car, neighbor's car, delivery trucks
- **Packages**: Tracked deliveries

## How It Works

1. AI analyzes event and extracts subject details
2. System matches against existing entities
3. New entities are created for unknown subjects
4. Events are linked to their entities

### Vehicle Extraction

Vehicles are identified by:
- **Color**: white, black, silver, red, blue, etc.
- **Make**: Toyota, Ford, Tesla, etc.
- **Model**: Camry, F-150, Model 3, etc.

Example: "white Toyota Camry" creates a unique entity.

## Managing Entities

### Viewing Entities

Navigate to **Entities** page to see all recognized entities:

- Filter by type (person, vehicle)
- View event history per entity
- See first/last seen timestamps

### Entity Details

Click an entity to view:

- All linked events with thumbnails
- Entity attributes (color, make, model for vehicles)
- Timeline of appearances

### Correcting Assignments

#### Unlinking Events

If an event is incorrectly assigned:

1. Open the entity detail page
2. Find the incorrect event
3. Click **Remove** to unlink it

#### Assigning Events

To add an unlinked event to an entity:

1. Open the event card
2. Click **Add to Entity**
3. Search for the correct entity
4. Confirm assignment

#### Merging Entities

If the same subject has multiple entities:

1. Go to **Entities** page
2. Select both entities (checkbox)
3. Click **Merge**
4. Choose which entity to keep
5. Confirm merge

## Learning from Corrections

ArgusAI stores manual corrections to improve future matching:

- Unlinks teach what doesn't match
- Assigns teach what does match
- Merges consolidate duplicates

This data helps refine entity detection over time.

## Named Entity Alerts

Create alerts for specific entities:

1. Go to entity detail page
2. Click **Create Alert Rule**
3. Configure notification settings
4. Save the rule

Now you'll be notified when that specific entity is detected.
