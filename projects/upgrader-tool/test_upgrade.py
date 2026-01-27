"""
pytest tests for upgrade.py
Run with: uv run pytest test_upgrade.py -v
"""
import json
import pytest
from upgrade import upgrade_asset


# Test fixtures
@pytest.fixture
def failing_asset():
    """FIP asset with procedures validation error"""
    return {
        "name": "behavior_775743_2025-03-21_08-54-07",
        "expected_success": False,
    }


@pytest.fixture
def successful_asset():
    """Ophys asset that should upgrade successfully"""
    return {
        "name": "single-plane-ophys_705363_2024-01-10_15-46-42",
        "expected_success": True,
    }


def test_failing_asset_returns_dict(failing_asset):
    """Test that failing asset returns a dict result"""
    result = upgrade_asset(failing_asset["name"])
    assert isinstance(result, dict), "Result should be a dict"


def test_failing_asset_has_required_keys(failing_asset):
    """Test that failing asset result has required keys"""
    result = upgrade_asset(failing_asset["name"])
    assert "success" in result
    assert "asset_identifier" in result
    assert "error" in result
    assert "traceback" in result


def test_failing_asset_success_is_false(failing_asset):
    """Test that failing asset has success=False"""
    result = upgrade_asset(failing_asset["name"])
    assert result["success"] is False


def test_failing_asset_is_json_serializable(failing_asset):
    """Test that failing asset result can be JSON serialized"""
    result = upgrade_asset(failing_asset["name"])
    try:
        json.dumps(result, default=str)
    except Exception as e:
        pytest.fail(f"Result is not JSON serializable: {e}")


def test_successful_asset_returns_dict(successful_asset):
    """Test that successful asset returns a dict result"""
    result = upgrade_asset(successful_asset["name"])
    assert isinstance(result, dict), "Result should be a dict"


def test_successful_asset_has_required_keys(successful_asset):
    """Test that successful asset result has required keys"""
    result = upgrade_asset(successful_asset["name"])
    assert "success" in result
    assert "asset_identifier" in result
    assert "upgraded_files" in result
    assert "unchanged_files" in result


def test_successful_asset_success_is_true(successful_asset):
    """Test that successful asset has success=True"""
    result = upgrade_asset(successful_asset["name"])
    assert result["success"] is True


def test_successful_asset_is_json_serializable(successful_asset):
    """Test that successful asset result can be JSON serialized"""
    result = upgrade_asset(successful_asset["name"])
    try:
        json.dumps(result, default=str)
    except Exception as e:
        pytest.fail(f"Result is not JSON serializable: {e}")


def test_successful_asset_has_data_fields(successful_asset):
    """Test that successful asset has original and upgraded data"""
    result = upgrade_asset(successful_asset["name"])
    assert "original_data" in result
    assert "upgraded_data" in result
    assert isinstance(result["original_data"], dict)
    assert isinstance(result["upgraded_data"], dict)


def test_successful_asset_data_is_json_serializable(successful_asset):
    """Test that data fields are JSON serializable"""
    result = upgrade_asset(successful_asset["name"])
    
    try:
        json.dumps(result["original_data"], default=str)
    except Exception as e:
        pytest.fail(f"original_data is not JSON serializable: {e}")
    
    try:
        json.dumps(result["upgraded_data"], default=str)
    except Exception as e:
        pytest.fail(f"upgraded_data is not JSON serializable: {e}")


def test_successful_asset_has_upgraded_files(successful_asset):
    """Test that successful asset lists upgraded files"""
    result = upgrade_asset(successful_asset["name"])
    assert len(result["upgraded_files"]) > 0, "Should have at least one upgraded file"


def test_invalid_asset_returns_error():
    """Test that invalid asset name returns appropriate error"""
    result = upgrade_asset("nonexistent_asset_12345")
    assert result["success"] is False
    assert "error" in result
    assert "not found" in result["error"].lower()
