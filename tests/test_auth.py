import pytest
import logging
from auth import load_whitelist, is_user_allowed

def test_load_valid_whitelist(tmp_path):
    """Load whitelist with valid user IDs."""
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text("123456789\n987654321\n")
    result = load_whitelist(str(whitelist_file))
    assert result == {123456789, 987654321}


def test_load_with_comments(tmp_path):
    """Parse file with comments correctly."""
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text(
        "# Admin users\n"
        "123456789\n"
        "\n"
        "# Friends\n"
        "987654321\n"
    )
    result = load_whitelist(str(whitelist_file))
    assert result == {123456789, 987654321}


def test_load_invalid_ids(tmp_path, caplog):
    """Skip invalid IDs, log warning."""
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text(
        "123456789\n"
        "invalid_id\n"
        "987654321\n"
    )
    result = load_whitelist(str(whitelist_file))
    assert result == {123456789, 987654321}
    assert "Invalid user ID in whitelist: invalid_id" in caplog.text


def test_empty_file_raises_error(tmp_path):
    """Empty file raises ValueError."""
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text("")
    with pytest.raises(ValueError, match="No valid user IDs found"):
        load_whitelist(str(whitelist_file))


def test_missing_file_raises_error(tmp_path):
    """Missing file raises FileNotFoundError."""
    whitelist_file = tmp_path / "nonexistent.txt"
    with pytest.raises(FileNotFoundError, match="whitelist.txt not found"):
        load_whitelist(str(whitelist_file))


def test_is_user_allowed_true():
    """Whitelisted user returns True."""
    whitelist = {123456789, 987654321}
    assert is_user_allowed(123456789, whitelist) is True


def test_is_user_allowed_false():
    """Non-whitelisted user returns False."""
    whitelist = {123456789, 987654321}
    assert is_user_allowed(111222333, whitelist) is False