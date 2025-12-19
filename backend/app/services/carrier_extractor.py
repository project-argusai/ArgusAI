"""
Carrier Extraction Service for Package Delivery Detection

Story P7-2.1: Add Carrier Detection to AI Analysis

This service extracts delivery carrier names from AI-generated event descriptions
using pattern matching. Supports FedEx, UPS, USPS, Amazon, and DHL carriers.

Performance:
    - Target: <10ms extraction time (regex-based)
    - Best-effort detection: failures do NOT block event processing
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Carrier detection patterns - compiled for performance
# Each pattern uses case-insensitive matching
CARRIER_PATTERNS = {
    'fedex': re.compile(
        r'\b(?:fed\s*ex|federal\s*express)\b',
        re.IGNORECASE
    ),
    'ups': re.compile(
        r'\b(?:ups|united\s*parcel(?:\s*service)?)\b',
        re.IGNORECASE
    ),
    'usps': re.compile(
        r'\b(?:usps|u\.?s\.?\s*postal(?:\s*service)?|mail\s*carrier|mailman|mail\s*truck|postal\s*worker|postal\s*carrier|postal\s*service)\b',
        re.IGNORECASE
    ),
    'amazon': re.compile(
        r'\b(?:amazon(?:\s*prime)?|prime\s*(?:van|truck|delivery))\b',
        re.IGNORECASE
    ),
    'dhl': re.compile(
        r'\b(?:dhl(?:\s*express)?)\b',
        re.IGNORECASE
    ),
}

# Human-readable display names for carriers
CARRIER_DISPLAY_NAMES = {
    'fedex': 'FedEx',
    'ups': 'UPS',
    'usps': 'USPS',
    'amazon': 'Amazon',
    'dhl': 'DHL',
}


def extract_carrier(description: str) -> Optional[str]:
    """
    Extract delivery carrier from AI-generated event description.

    Uses regex pattern matching to identify carrier names, logos, uniforms,
    or truck references in the description text.

    Args:
        description: AI-generated event description text

    Returns:
        Lowercase carrier name ('fedex', 'ups', 'usps', 'amazon', 'dhl')
        or None if no carrier detected

    Performance:
        Completes in <10ms (target from tech spec)

    Example:
        >>> extract_carrier("A FedEx driver approached the door with a package")
        'fedex'
        >>> extract_carrier("A person walked across the driveway")
        None
    """
    if not description:
        return None

    # Check patterns in order (first match wins)
    # Order: FedEx, UPS, USPS, Amazon, DHL (most common carriers first)
    for carrier, pattern in CARRIER_PATTERNS.items():
        if pattern.search(description):
            logger.debug(
                f"Carrier detected: {carrier}",
                extra={"carrier": carrier, "description_preview": description[:100]}
            )
            return carrier

    return None


def get_carrier_display_name(carrier: Optional[str]) -> Optional[str]:
    """
    Get human-readable display name for a carrier.

    Args:
        carrier: Lowercase carrier name from extract_carrier()

    Returns:
        Display name (e.g., 'FedEx', 'UPS') or None if carrier is None/unknown
    """
    if not carrier:
        return None
    return CARRIER_DISPLAY_NAMES.get(carrier)
