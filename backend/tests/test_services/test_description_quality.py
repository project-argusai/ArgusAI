"""
Tests for Story P3-6.2: Detect Vague Descriptions

Tests cover:
- AC1: Detect vague phrase patterns (case-insensitive)
- AC2: Detect insufficient detail (short descriptions, generic phrases)
- AC3: Set low_confidence flag on vague descriptions
- AC4: Track vagueness reason
- AC5: Allow specific descriptions through
"""
import pytest
from app.services.description_quality import (
    detect_vague_description,
    get_vague_phrases,
    get_generic_phrases,
    get_min_word_count,
    MIN_WORD_COUNT,
    VAGUE_PHRASES,
    GENERIC_PHRASES,
)


class TestVaguePhraseDetection:
    """AC1: Test vague phrase pattern detection"""

    @pytest.mark.parametrize("phrase,expected_phrase_name", [
        # All descriptions must have 10+ words to avoid triggering short description check first
        ("It appears to be a person walking by the front door area", "appears to be"),
        ("The object possibly belongs to a visitor who came by today", "possibly"),
        ("Image quality is unclear and we cannot see the person clearly", "unclear"),
        ("Cannot determine the identity of the subject in this image frame", "cannot determine"),
        ("Something is moving in the driveway near the parked cars today", "something"),
        ("Motion detected in the front yard near the mailbox and trees", "motion detected"),
        ("It might be a delivery driver coming to drop off a package", "might be"),
        ("Could be a neighbor checking the mailbox or walking their dog today", "could be"),
        ("It seems like someone is at the door waiting for a response", "seems like"),
        ("Hard to tell what is happening in this frame due to motion", "hard to tell"),
    ])
    def test_vague_phrase_detected(self, phrase, expected_phrase_name):
        """Each vague phrase pattern should be detected"""
        is_vague, reason = detect_vague_description(phrase)
        assert is_vague is True
        assert reason is not None
        assert expected_phrase_name in reason.lower()

    def test_case_insensitive_detection(self):
        """AC1: Detection should be case-insensitive"""
        test_cases = [
            # All descriptions must have 10+ words to avoid triggering short description check
            "It APPEARS TO BE something moving near the front door area today",
            "Appears To Be a vehicle parked in the driveway near the garage",
            "The situation appears to be unclear based on the image quality",
            "There is POSSIBLY a person walking down the sidewalk toward house",
            "Possibly A VEHICLE driving past the house on the street today",
        ]
        for phrase in test_cases:
            is_vague, reason = detect_vague_description(phrase)
            assert is_vague is True, f"Failed to detect vague phrase in: {phrase}"

    def test_motion_detected_with_subject_not_vague(self):
        """AC1: 'motion detected' followed by specific subject should NOT be vague"""
        # These should NOT be flagged as vague (have specific subjects)
        specific_descriptions = [
            "Motion detected: person walking toward the house with package in hand",
            "Motion detected. A vehicle appears in the driveway area with headlights on.",
            "Motion detected with delivery driver placing package at door",
            "Motion detected - animal crossing the yard looks like a cat",
        ]
        for desc in specific_descriptions:
            is_vague, reason = detect_vague_description(desc)
            # Should pass (reason may be set due to word count or other vague phrases)
            # The key test is that "motion detected" alone doesn't trigger vagueness
            if reason and "motion detected" in reason.lower():
                pytest.fail(f"'motion detected' should not trigger when followed by subject: {desc}")


class TestShortDescriptionDetection:
    """AC2: Test insufficient detail detection (word count)"""

    def test_empty_description(self):
        """Empty description should be flagged"""
        is_vague, reason = detect_vague_description("")
        assert is_vague is True
        assert "empty" in reason.lower()

    def test_very_short_description(self):
        """Descriptions under minimum word count should be flagged"""
        short_descriptions = [
            "Motion happened here.",
            "Person walking today.",
            "A person moved.",
            "Activity in yard now.",
            "Motion at door area.",
            "Three words here only.",
            "Five total words here now.",
        ]
        for desc in short_descriptions:
            is_vague, reason = detect_vague_description(desc)
            assert is_vague is True, f"Short description should be flagged: {desc}"
            # Reason should mention "short" or "words" or "generic" (if it matches generic pattern)
            assert "short" in reason.lower() or "words" in reason.lower() or "generic" in reason.lower(), f"Unexpected reason: {reason}"

    def test_exact_minimum_word_count(self):
        """Description with exactly MIN_WORD_COUNT words should NOT be flagged for length"""
        # Create a description with exactly MIN_WORD_COUNT words
        words = ["Person", "walking", "toward", "front", "door", "carrying", "large", "brown", "box", "quickly"]
        assert len(words) == MIN_WORD_COUNT
        desc = " ".join(words)

        is_vague, reason = detect_vague_description(desc)
        # Should not be flagged for length (may still be flagged for other reasons)
        if is_vague and reason:
            assert "short" not in reason.lower()

    def test_whitespace_normalization(self):
        """Extra whitespace should be normalized before word counting"""
        # Description with lots of extra whitespace
        desc = "   Person    walking    toward    door    carrying    a    large    brown    cardboard    box   "
        is_vague, reason = detect_vague_description(desc)
        # Should count as 10 words, not flagged for length
        if is_vague and reason:
            assert "short" not in reason.lower()


class TestGenericPhraseDetection:
    """AC2: Test generic phrase detection"""

    @pytest.mark.parametrize("phrase,expected_phrase_name", [
        ("Activity detected", "activity detected"),
        ("Activity detected.", "activity detected"),
        ("ACTIVITY DETECTED", "activity detected"),
        ("Movement observed", "movement observed"),
        ("Movement observed.", "movement observed"),
        ("Something moved", "something moved"),
        ("Something moved.", "something moved"),
        ("Motion detected", "motion detected"),
        ("Motion detected.", "motion detected"),
        ("Object detected", "object detected"),
        ("Object detected.", "object detected"),
        ("Movement detected", "movement detected"),
        ("Movement detected.", "movement detected"),
    ])
    def test_generic_phrase_detected(self, phrase, expected_phrase_name):
        """Generic phrases (entire description) should be detected"""
        is_vague, reason = detect_vague_description(phrase)
        assert is_vague is True
        assert reason is not None
        assert "generic" in reason.lower() or expected_phrase_name in reason.lower()


class TestSpecificDescriptionsPassThrough:
    """AC5: Test that specific descriptions are NOT flagged"""

    @pytest.mark.parametrize("description", [
        "Person in blue jacket delivered package to front door and rang doorbell",
        "Large brown delivery truck stopped at the curb with driver exiting vehicle",
        "Two people walking down the driveway toward the street in conversation",
        "White sedan pulled into driveway and parked near the garage door opening",
        "Golden retriever dog running across front yard chasing after a squirrel",
        "Mail carrier in uniform placing letters in mailbox at end of driveway",
        "Child on bicycle riding down sidewalk past the front yard area quickly",
        "FedEx delivery driver scanning package barcode at front porch before leaving",
        "Neighbor walking dog on leash past house heading toward park area slowly",
        "Amazon delivery van stopping at curb with driver retrieving package from back",
    ])
    def test_specific_description_not_flagged(self, description):
        """Specific, detailed descriptions should NOT be flagged as vague"""
        is_vague, reason = detect_vague_description(description)
        assert is_vague is False, f"Specific description should not be flagged: {description}"
        assert reason is None


class TestVagueReasonFormat:
    """AC4: Test vague_reason field format"""

    def test_vague_phrase_reason_format(self):
        """Vague phrase reason should be human-readable"""
        is_vague, reason = detect_vague_description("It appears to be someone walking in the yard area today")
        assert is_vague is True
        assert "Contains vague phrase:" in reason
        assert "'appears to be'" in reason

    def test_short_description_reason_format(self):
        """Short description reason should include word count"""
        is_vague, reason = detect_vague_description("Person walking.")
        assert is_vague is True
        assert "short" in reason.lower() or "words" in reason.lower()
        # Should include actual word count and minimum
        assert "2" in reason or "words" in reason

    def test_generic_phrase_reason_format(self):
        """Generic phrase reason should be descriptive"""
        is_vague, reason = detect_vague_description("Activity detected.")
        assert is_vague is True
        assert "generic" in reason.lower() or "activity detected" in reason.lower()


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_none_like_values(self):
        """None and empty-like values should be handled gracefully"""
        # Empty string
        is_vague, reason = detect_vague_description("")
        assert is_vague is True

        # Whitespace only
        is_vague, reason = detect_vague_description("   ")
        assert is_vague is True

    def test_unicode_characters(self):
        """Unicode characters should be handled properly"""
        desc = "Person with café cup walking toward house carrying laptop and briefcase"
        is_vague, reason = detect_vague_description(desc)
        assert is_vague is False

    def test_numbers_in_description(self):
        """Numbers should be counted as words"""
        desc = "2 people standing at door 3 packages on porch 1 car in driveway"
        is_vague, reason = detect_vague_description(desc)
        # Should have enough words (13 words)
        if is_vague:
            assert "short" not in reason.lower()

    def test_punctuation_handling(self):
        """Punctuation should not affect word counting"""
        desc = "Person, walking, toward, the, front, door, carrying, a, large, package."
        is_vague, reason = detect_vague_description(desc)
        # Should count 10 words
        if is_vague:
            assert "short" not in reason.lower()


class TestHelperFunctions:
    """Test helper functions for documentation/UI"""

    def test_get_vague_phrases_returns_list(self):
        """get_vague_phrases should return list of phrase names"""
        phrases = get_vague_phrases()
        assert isinstance(phrases, list)
        assert len(phrases) > 0
        assert "appears to be" in phrases

    def test_get_generic_phrases_returns_list(self):
        """get_generic_phrases should return list of phrase names"""
        phrases = get_generic_phrases()
        assert isinstance(phrases, list)
        assert len(phrases) > 0
        assert "activity detected" in phrases

    def test_get_min_word_count_returns_int(self):
        """get_min_word_count should return the threshold"""
        count = get_min_word_count()
        assert isinstance(count, int)
        assert count == MIN_WORD_COUNT
        assert count == 10


class TestCombinedVagueConditions:
    """Test when multiple vague conditions apply"""

    def test_short_and_vague_phrase(self):
        """Short description with vague phrase should be detected"""
        # Only 3 words with vague phrase
        is_vague, reason = detect_vague_description("Possibly a person.")
        assert is_vague is True
        # Should be flagged for being short (checked first after generic)
        # or for containing vague phrase
        assert reason is not None

    def test_generic_takes_precedence(self):
        """Generic phrase detection should take precedence"""
        is_vague, reason = detect_vague_description("Motion detected.")
        assert is_vague is True
        assert "generic" in reason.lower() or "motion detected" in reason.lower()


class TestLowConfidenceIntegration:
    """AC3: Test low_confidence flag integration with vagueness"""

    def test_vague_description_should_trigger_low_confidence(self):
        """When description is vague, low_confidence should be set"""
        # This tests the logic that _store_protect_event should implement
        # The detect_vague_description function returns (is_vague, reason)
        # which should be used to set low_confidence = True

        test_cases = [
            ("It appears to be a person standing there today", True),
            ("Motion detected.", True),
            ("Short description here.", True),
            ("Person in blue jacket delivered package to front door area", False),
        ]

        for desc, expected_vague in test_cases:
            is_vague, reason = detect_vague_description(desc)
            assert is_vague == expected_vague, f"Expected is_vague={expected_vague} for: {desc}"

            # If vague, reason should be set
            if expected_vague:
                assert reason is not None
            else:
                assert reason is None
