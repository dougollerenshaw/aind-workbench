"""
Tests for upgrade.py functionality.
"""

import pytest
from upgrade import upgrade_asset


def test_successful_asset():
    """Test an asset that should upgrade successfully."""
    result = upgrade_asset("single-plane-ophys_705363_2024-01-10_15-46-42")

    assert result["success"] is True
    assert len(result["successful_fields"]) > 0
    assert len(result["failed_fields"]) == 0


def test_partially_failing_asset():
    """Test an asset that partially fails - some fields upgrade, others don't."""
    result = upgrade_asset("behavior_746346_2025-03-12_17-21-50")

    assert result["success"] is False
    assert result["partial_success"] is True
    assert len(result["successful_fields"]) > 0
    assert len(result["failed_fields"]) > 0

    # For this specific asset, we know data_description and subject should succeed
    assert "data_description" in result["successful_fields"]
    assert "subject" in result["successful_fields"]

    # And procedures should fail
    assert "procedures" in result["failed_fields"]


def test_field_results_structure():
    """Test that field results have the correct structure."""
    result = upgrade_asset("behavior_746346_2025-03-12_17-21-50")

    field_results = result.get("field_results", {})
    assert len(field_results) > 0

    # Check successful field structure
    for field_name in result["successful_fields"]:
        field_result = field_results[field_name]
        assert field_result["success"] is True
        assert "original" in field_result
        assert "upgraded" in field_result

    # Check failed field structure
    for field_name in result["failed_fields"]:
        field_result = field_results[field_name]
        assert field_result["success"] is False
        assert "original" in field_result
        assert "error" in field_result


def test_field_conversion():
    """Test that field name conversions (session->acquisition, rig->instrument) are recorded."""
    result = upgrade_asset("single-plane-ophys_705363_2024-01-10_15-46-42")

    field_results = result.get("field_results", {})

    # Check if session was converted to acquisition
    if "session" in field_results:
        session_result = field_results["session"]
        if session_result["success"]:
            assert session_result.get("converted_to") == "acquisition"

    # Check if rig was converted to instrument
    if "rig" in field_results:
        rig_result = field_results["rig"]
        if rig_result["success"]:
            assert rig_result.get("converted_to") == "instrument"


def test_skip_missing_fields():
    """Test that fields not present in original asset are skipped entirely."""
    result = upgrade_asset("behavior_746346_2025-03-12_17-21-50")

    field_results = result.get("field_results", {})

    # All fields in results should have original data
    for field_name, field_result in field_results.items():
        assert (
            field_result.get("original") is not None
        ), f"Field {field_name} has no original data - should have been skipped"
