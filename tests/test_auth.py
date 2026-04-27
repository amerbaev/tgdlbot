import pytest
from auth import load_whitelist

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