"""
Frame Annotation Service (Story P15-5.2)

Draws bounding boxes and labels on camera frames for visual feedback
on AI-detected objects. Uses Pillow for drawing operations.

ADR-P15-007: FrameAnnotationService Design
- Uses normalized coordinates (0-1) for resolution independence
- Color-coded by entity type for visual distinction
- Labels include entity type and confidence percentage
- White background on labels for readability on any image
"""
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from PIL import Image, ImageDraw, ImageFont

from app.core.decorators import singleton

logger = logging.getLogger(__name__)


@singleton
class FrameAnnotationService:
    """
    Service to draw bounding boxes and labels on camera frames.

    Entity Type Color Palette (from tech spec):
    - person: Blue (#3B82F6) - RGB (59, 130, 246)
    - vehicle: Green (#22C55E) - RGB (34, 197, 94)
    - package: Orange (#F97316) - RGB (249, 115, 22)
    - animal: Purple (#A855F7) - RGB (168, 85, 247)
    - other: Gray (#9CA3AF) - RGB (156, 163, 175)
    """

    # Entity type to RGB color mapping
    COLORS: Dict[str, Tuple[int, int, int]] = {
        "person": (59, 130, 246),    # Blue
        "vehicle": (34, 197, 94),    # Green
        "package": (249, 115, 22),   # Orange
        "animal": (168, 85, 247),    # Purple
        "other": (156, 163, 175),    # Gray
    }

    # Box stroke width in pixels
    STROKE_WIDTH = 2

    # Font settings
    FONT_SIZE = 14
    LABEL_PADDING = 2

    def __init__(self):
        """Initialize the annotation service."""
        self._font: Optional[ImageFont.FreeTypeFont] = None
        logger.info("FrameAnnotationService initialized")

    def _get_font(self) -> ImageFont.FreeTypeFont:
        """
        Get the font for drawing labels.

        Falls back to default font if custom fonts unavailable.
        """
        if self._font is None:
            try:
                # Try to load a common system font
                self._font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", self.FONT_SIZE)
            except OSError:
                try:
                    # Try macOS font
                    self._font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", self.FONT_SIZE)
                except OSError:
                    # Fall back to default font (may be smaller)
                    self._font = ImageFont.load_default()
                    logger.warning("Using default font - labels may appear smaller")
        return self._font

    def _get_color(self, entity_type: str) -> Tuple[int, int, int]:
        """Get color for entity type, defaulting to 'other' color."""
        return self.COLORS.get(entity_type.lower(), self.COLORS["other"])

    def _draw_label(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        y: int,
        color: Tuple[int, int, int]
    ) -> None:
        """
        Draw a label with white background for readability.

        Args:
            draw: ImageDraw object
            text: Label text
            x: X coordinate for label start
            y: Y coordinate for label top
            color: RGB color tuple for text
        """
        font = self._get_font()

        # Get text bounding box
        bbox = draw.textbbox((x, y), text, font=font)

        # Draw white background rectangle (with padding)
        draw.rectangle(
            [
                bbox[0] - self.LABEL_PADDING,
                bbox[1] - self.LABEL_PADDING,
                bbox[2] + self.LABEL_PADDING,
                bbox[3] + self.LABEL_PADDING
            ],
            fill=(255, 255, 255)
        )

        # Draw text
        draw.text((x, y), text, fill=color, font=font)

    def annotate_frame(
        self,
        frame_path: str,
        bounding_boxes: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Draw bounding boxes on frame and save as annotated version.

        Args:
            frame_path: Path to the original frame image
            bounding_boxes: List of bounding box dictionaries with keys:
                - x, y, width, height: Normalized coordinates (0-1)
                - entity_type: Type of detected object
                - confidence: Detection confidence (0-1)
                - label: Description text

        Returns:
            Path to annotated frame, or None if annotation fails
        """
        if not bounding_boxes:
            logger.debug("No bounding boxes provided, skipping annotation")
            return None

        original_path = Path(frame_path)
        if not original_path.exists():
            logger.error(f"Frame not found: {frame_path}")
            return None

        try:
            # Open image
            img = Image.open(original_path)
            draw = ImageDraw.Draw(img)
            width, height = img.size

            logger.debug(
                f"Annotating frame with {len(bounding_boxes)} bounding boxes",
                extra={
                    "frame_path": str(original_path),
                    "image_size": f"{width}x{height}",
                    "box_count": len(bounding_boxes)
                }
            )

            # Draw each bounding box
            for box in bounding_boxes:
                try:
                    # Convert normalized coordinates to pixel coordinates
                    x1 = int(box["x"] * width)
                    y1 = int(box["y"] * height)
                    x2 = int((box["x"] + box["width"]) * width)
                    y2 = int((box["y"] + box["height"]) * height)

                    entity_type = box.get("entity_type", "other")
                    confidence = box.get("confidence", 0)
                    label_text = box.get("label", entity_type)

                    # Get color for this entity type
                    color = self._get_color(entity_type)

                    # Draw rectangle (bounding box)
                    draw.rectangle(
                        [x1, y1, x2, y2],
                        outline=color,
                        width=self.STROKE_WIDTH
                    )

                    # Prepare label with entity type and confidence
                    label = f"{entity_type} {int(confidence * 100)}%"

                    # Position label above the box (or inside if at top edge)
                    label_y = y1 - self.FONT_SIZE - self.LABEL_PADDING * 2 - 2
                    if label_y < 0:
                        label_y = y1 + 2  # Put inside box if at top

                    # Draw label
                    self._draw_label(draw, label, x1, label_y, color)

                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"Invalid bounding box data, skipping: {e}")
                    continue

            # Generate annotated file path
            annotated_path = self._get_annotated_path(original_path)

            # Save annotated image
            img.save(str(annotated_path), quality=90)

            logger.info(
                f"Frame annotated successfully",
                extra={
                    "original_path": str(original_path),
                    "annotated_path": str(annotated_path),
                    "box_count": len(bounding_boxes)
                }
            )

            return str(annotated_path)

        except Exception as e:
            logger.error(
                f"Failed to annotate frame: {e}",
                extra={
                    "frame_path": str(original_path),
                    "error": str(e)
                },
                exc_info=True
            )
            return None

    def _get_annotated_path(self, original_path: Path) -> Path:
        """
        Generate annotated file path from original path.

        Adds '_annotated' suffix before file extension.
        Example: frame_0.jpg -> frame_0_annotated.jpg
        """
        stem = original_path.stem
        suffix = original_path.suffix
        return original_path.parent / f"{stem}_annotated{suffix}"

    def annotate_frames(
        self,
        frame_paths: List[str],
        bounding_boxes_per_frame: List[Optional[List[Dict[str, Any]]]]
    ) -> List[Optional[str]]:
        """
        Annotate multiple frames with their respective bounding boxes.

        Args:
            frame_paths: List of paths to original frames
            bounding_boxes_per_frame: List of bounding box lists, one per frame.
                Can be None for frames without annotations.

        Returns:
            List of annotated frame paths (or None for frames that failed/skipped)
        """
        if len(frame_paths) != len(bounding_boxes_per_frame):
            logger.error("Mismatch between frame count and bounding box count")
            return [None] * len(frame_paths)

        annotated_paths = []
        for frame_path, boxes in zip(frame_paths, bounding_boxes_per_frame):
            if boxes:
                annotated_path = self.annotate_frame(frame_path, boxes)
            else:
                annotated_path = None
            annotated_paths.append(annotated_path)

        return annotated_paths

    def get_entity_colors(self) -> Dict[str, Dict[str, Any]]:
        """
        Get entity type colors for frontend legend display.

        Returns:
            Dictionary mapping entity types to color info (hex and RGB)
        """
        return {
            entity_type: {
                "rgb": color,
                "hex": "#{:02x}{:02x}{:02x}".format(*color)
            }
            for entity_type, color in self.COLORS.items()
        }


def get_frame_annotation_service() -> FrameAnnotationService:
    """Get singleton instance of FrameAnnotationService."""
    return FrameAnnotationService()


def reset_frame_annotation_service() -> None:
    """Reset the global FrameAnnotationService instance (for testing)."""
    FrameAnnotationService._reset_instance()
