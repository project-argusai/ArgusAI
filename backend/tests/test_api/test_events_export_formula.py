"""Unit tests for events CSV formula neutralization (#602 / CR-012)."""
from app.api.v1.events import _csv_formula_safe


def test_csv_formula_safe_prefixes_dangerous_prefixes():
    for prefix in ("=", "+", "-", "@"):
        assert _csv_formula_safe(f"{prefix}1+1") == f"'{prefix}1+1"


def test_csv_formula_safe_leaves_normal_text():
    assert _csv_formula_safe("Person at door") == "Person at door"
    assert _csv_formula_safe("") == ""
    assert _csv_formula_safe(None) == ""
    assert _csv_formula_safe(42) == "42"
