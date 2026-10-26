# SPDX-License-Identifier: GPL-3.0-or-later


from sftp_tools.formatting import format_size
from sftp_tools.settings import AppSettings, SizeFormat


def test_format_size_auto_mode_bytes():
    """Auto mode: bytes without separator."""
    settings = AppSettings(size_format=SizeFormat(format="auto", thousands_separator=False))
    assert format_size(512, settings) == "512"


def test_format_size_auto_mode_kilobytes():
    """Auto mode: kilobytes."""
    settings = AppSettings(size_format=SizeFormat(format="auto", thousands_separator=False, decimal_places=1))
    assert format_size(1536, settings) == "1.5 KB"


def test_format_size_auto_mode_megabytes():
    """Auto mode: megabytes."""
    settings = AppSettings(size_format=SizeFormat(format="auto", thousands_separator=False, decimal_places=1))
    assert format_size(26_214_400, settings) == "25.0 MB"  # 25 MB


def test_format_size_auto_mode_gigabytes():
    """Auto mode: gigabytes."""
    settings = AppSettings(size_format=SizeFormat(format="auto", thousands_separator=False, decimal_places=1))
    assert format_size(1_288_490_188, settings) == "1.2 GB"  # ~1.2 GB


def test_format_size_binary_mode():
    """Binary mode with KiB, MiB, GiB units."""
    settings = AppSettings(size_format=SizeFormat(format="binary", thousands_separator=False, decimal_places=1))
    assert format_size(1024, settings) == "1.0 KiB"
    assert format_size(1024 * 1024, settings) == "1.0 MiB"
    assert format_size(1024 * 1024 * 1024, settings) == "1.0 GiB"


def test_format_size_decimal_mode():
    """Decimal mode with KB, MB, GB units (1000-based)."""
    settings = AppSettings(size_format=SizeFormat(format="decimal", thousands_separator=False, decimal_places=1))
    assert format_size(1000, settings) == "1.0 KB"
    assert format_size(1000 * 1000, settings) == "1.0 MB"
    assert format_size(1000 * 1000 * 1000, settings) == "1.0 GB"


def test_format_size_with_thousands_separator():
    """Test thousands separator in all modes."""
    settings = AppSettings(size_format=SizeFormat(format="auto", thousands_separator=True, decimal_places=1))
    assert format_size(512, settings) == "512"  # bytes (no separator needed for small numbers)
    assert format_size(150_000, settings) == "146.5 KB"  # ~146.5 KB (in KB range)
    
    # Test with decimal mode to avoid auto-conversion to MB
    settings = AppSettings(size_format=SizeFormat(format="decimal", thousands_separator=True, decimal_places=1))
    assert format_size(1_500_000, settings) == "1.5 MB"


def test_format_size_decimal_places():
    """Test different decimal place settings."""
    # 0 decimal places
    settings = AppSettings(size_format=SizeFormat(format="auto", thousands_separator=False, decimal_places=0))
    assert format_size(1_536, settings) == "2 KB"  # 1.5 rounded to 2
    
    # 2 decimal places
    settings = AppSettings(size_format=SizeFormat(format="auto", thousands_separator=False, decimal_places=2))
    assert format_size(1_536, settings) == "1.50 KB"


def test_format_size_zero():
    """Test zero size."""
    settings = AppSettings()
    assert format_size(0, settings) == "0"


def test_format_size_negative():
    """Test negative size (should be treated as 0)."""
    settings = AppSettings()
    assert format_size(-100, settings) == "0"


def test_format_size_large_numbers():
    """Test very large file sizes."""
    # 1 TB in decimal mode
    settings = AppSettings(size_format=SizeFormat(format="decimal", thousands_separator=False, decimal_places=1))
    assert format_size(1_000_000_000_000, settings) == "1.0 TB"
    
    # 1 TiB in binary mode
    settings = AppSettings(size_format=SizeFormat(format="binary", thousands_separator=False, decimal_places=1))
    assert format_size(1024 ** 4, settings) == "1.0 TiB"
