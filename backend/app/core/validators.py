"""
Validation helpers for FastAPI endpoints.

Story P14-2.5: Add UUID Validation on Path Parameters
Provides reusable type annotations for path parameters with built-in validation.
"""
from uuid import UUID
from fastapi import Path
from typing import Annotated


# Reusable UUID path parameter with OpenAPI documentation
# Usage: async def get_camera(camera_id: UUIDPath):
UUIDPath = Annotated[
    UUID,
    Path(
        description="Resource UUID",
        example="550e8400-e29b-41d4-a716-446655440000"
    )
]

# Specific validators for common entity types (for better OpenAPI docs)
CameraUUID = Annotated[
    UUID,
    Path(description="Camera UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

EventUUID = Annotated[
    UUID,
    Path(description="Event UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

AlertRuleUUID = Annotated[
    UUID,
    Path(description="Alert Rule UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

ControllerUUID = Annotated[
    UUID,
    Path(description="Protect Controller UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

EntityUUID = Annotated[
    UUID,
    Path(description="Recognized Entity UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

NotificationUUID = Annotated[
    UUID,
    Path(description="Notification UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

DeviceUUID = Annotated[
    UUID,
    Path(description="Device UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

SummaryUUID = Annotated[
    UUID,
    Path(description="Summary UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

DigestUUID = Annotated[
    UUID,
    Path(description="Digest UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

APIKeyUUID = Annotated[
    UUID,
    Path(description="API Key UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

PersonUUID = Annotated[
    UUID,
    Path(description="Person UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

VehicleUUID = Annotated[
    UUID,
    Path(description="Vehicle UUID", example="550e8400-e29b-41d4-a716-446655440000")
]

PairingUUID = Annotated[
    UUID,
    Path(description="Pairing UUID", example="550e8400-e29b-41d4-a716-446655440000")
]
