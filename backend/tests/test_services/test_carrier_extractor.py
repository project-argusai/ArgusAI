"""
Tests for Carrier Extraction Service

Story P7-2.1: Add Carrier Detection to AI Analysis

Tests carrier name extraction from AI-generated event descriptions.
"""

import pytest
from app.services.carrier_extractor import (
    extract_carrier,
    get_carrier_display_name,
    CARRIER_PATTERNS,
    CARRIER_DISPLAY_NAMES,
)


class TestCarrierExtraction:
    """Test carrier extraction from descriptions"""

    # FedEx variations (10+ test cases)
    @pytest.mark.parametrize("description,expected", [
        ("A FedEx driver approached the front door", "fedex"),
        ("fedex delivery person left a package", "fedex"),
        ("FEDEX truck pulled up", "fedex"),
        ("The Fed Ex driver rang the doorbell", "fedex"),
        ("Federal Express delivery at 3pm", "fedex"),
        ("FedEx ground truck in driveway", "fedex"),
        ("Package delivered by fedex", "fedex"),
        ("A man wearing FedEx uniform", "fedex"),
        ("The FedEx van parked on street", "fedex"),
        ("Received fedex package today", "fedex"),
        ("The FED EX driver left", "fedex"),
    ])
    def test_fedex_detection(self, description, expected):
        """Test FedEx carrier detection with various patterns"""
        assert extract_carrier(description) == expected

    # UPS variations
    @pytest.mark.parametrize("description,expected", [
        ("A UPS driver delivered a package", "ups"),
        ("ups truck in the driveway", "ups"),
        ("Brown UPS van approaching", "ups"),
        ("United Parcel Service delivery", "ups"),
        ("The UPS person rang bell", "ups"),
        ("Person in UPS uniform", "ups"),
        ("Delivery from UPS at noon", "ups"),
        ("United parcel truck arrived", "ups"),
        ("UPS left package at door", "ups"),
        ("The UPS guy came by", "ups"),
    ])
    def test_ups_detection(self, description, expected):
        """Test UPS carrier detection with various patterns"""
        assert extract_carrier(description) == expected

    # USPS variations
    @pytest.mark.parametrize("description,expected", [
        ("USPS mail carrier approaching", "usps"),
        ("The mailman delivered letters", "usps"),
        ("Mail carrier at the door", "usps"),
        ("US Postal Service truck", "usps"),
        ("usps delivery person", "usps"),
        ("Postal worker leaving mail", "usps"),
        ("Mail truck on the street", "usps"),
        ("The postal carrier arrived", "usps"),
        ("USPS package delivery", "usps"),
        ("Mailman placed package on porch", "usps"),
        ("Postal service delivery", "usps"),
    ])
    def test_usps_detection(self, description, expected):
        """Test USPS carrier detection with various patterns"""
        assert extract_carrier(description) == expected

    # Amazon variations
    @pytest.mark.parametrize("description,expected", [
        ("Amazon delivery driver", "amazon"),
        ("amazon van in driveway", "amazon"),
        ("Person in Amazon blue vest", "amazon"),
        ("Amazon Prime delivery", "amazon"),
        ("Prime van approaching", "amazon"),
        ("AMAZON package left at door", "amazon"),
        ("Amazon delivery person", "amazon"),
        ("Prime delivery truck", "amazon"),
        ("The Amazon driver arrived", "amazon"),
        ("Delivery by Amazon at 2pm", "amazon"),
    ])
    def test_amazon_detection(self, description, expected):
        """Test Amazon carrier detection with various patterns"""
        assert extract_carrier(description) == expected

    # DHL variations
    @pytest.mark.parametrize("description,expected", [
        ("DHL driver at the door", "dhl"),
        ("dhl express truck arriving", "dhl"),
        ("Yellow DHL van in driveway", "dhl"),
        ("DHL Express package delivery", "dhl"),
        ("Person in DHL uniform", "dhl"),
        ("DHL courier rang doorbell", "dhl"),
        ("Package delivered by DHL", "dhl"),
        ("The DHL truck arrived", "dhl"),
        ("DHL express delivery", "dhl"),
        ("A DHL delivery person", "dhl"),
    ])
    def test_dhl_detection(self, description, expected):
        """Test DHL carrier detection with various patterns"""
        assert extract_carrier(description) == expected

    # Non-delivery descriptions
    @pytest.mark.parametrize("description", [
        "A person walked across the driveway",
        "Car parked in the street",
        "Dog running in the yard",
        "Person at the front door",
        "Package on the porch",
        "Delivery person left a package",  # No specific carrier
        "Someone rang the doorbell",
        "Vehicle approaching the house",
        "",
    ])
    def test_no_carrier_detection(self, description):
        """Test that non-carrier descriptions return None"""
        assert extract_carrier(description) is None

    def test_none_description(self):
        """Test that None description returns None"""
        assert extract_carrier(None) is None

    def test_first_carrier_wins(self):
        """Test that when multiple carriers mentioned, first one is returned"""
        description = "FedEx and UPS trucks both in the driveway"
        assert extract_carrier(description) == "fedex"

    def test_case_insensitive_matching(self):
        """Test case-insensitive matching for all cases"""
        assert extract_carrier("FEDEX delivery") == "fedex"
        assert extract_carrier("FedEx delivery") == "fedex"
        assert extract_carrier("fedex delivery") == "fedex"
        assert extract_carrier("FeDex delivery") == "fedex"


class TestCarrierDisplayName:
    """Test carrier display name conversion"""

    @pytest.mark.parametrize("carrier,expected", [
        ("fedex", "FedEx"),
        ("ups", "UPS"),
        ("usps", "USPS"),
        ("amazon", "Amazon"),
        ("dhl", "DHL"),
    ])
    def test_display_names(self, carrier, expected):
        """Test that carriers have correct display names"""
        assert get_carrier_display_name(carrier) == expected

    def test_none_carrier(self):
        """Test that None carrier returns None"""
        assert get_carrier_display_name(None) is None

    def test_unknown_carrier(self):
        """Test that unknown carrier returns None"""
        assert get_carrier_display_name("unknown_carrier") is None


class TestCarrierPatterns:
    """Test carrier pattern definitions"""

    def test_all_carriers_have_patterns(self):
        """Test that all supported carriers have patterns defined"""
        expected_carriers = {"fedex", "ups", "usps", "amazon", "dhl"}
        assert set(CARRIER_PATTERNS.keys()) == expected_carriers

    def test_all_carriers_have_display_names(self):
        """Test that all supported carriers have display names"""
        expected_carriers = {"fedex", "ups", "usps", "amazon", "dhl"}
        assert set(CARRIER_DISPLAY_NAMES.keys()) == expected_carriers

    def test_patterns_are_compiled_regex(self):
        """Test that all patterns are compiled regex objects"""
        import re
        for carrier, pattern in CARRIER_PATTERNS.items():
            assert isinstance(pattern, re.Pattern), f"{carrier} pattern is not compiled"


class TestCarrierExtractionPerformance:
    """Test carrier extraction performance"""

    def test_extraction_performance(self):
        """Test that extraction completes quickly (<10ms target)"""
        import time

        descriptions = [
            "A FedEx driver approached the front door with a package",
            "Person walking across the driveway",
            "UPS delivery at noon",
            "USPS mail carrier delivering letters",
            "Amazon van parked on street",
        ]

        start = time.perf_counter()
        for description in descriptions * 100:  # 500 iterations
            extract_carrier(description)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Should complete 500 extractions in <100ms (0.2ms per extraction avg)
        assert elapsed_ms < 100, f"Extraction took {elapsed_ms:.2f}ms for 500 iterations"
