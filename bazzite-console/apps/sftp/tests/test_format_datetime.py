# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for format_datetime function."""

import re
from datetime import datetime

from sftp_tools.formatting import format_datetime
from sftp_tools.settings import AppSettings


def test_format_datetime_iso_hms():
    """Test ISO date format with HH:MM:SS."""
    settings = AppSettings(date_format="YYYY-MM-DD", time_format="HH:MM:SS")
    # Use current time to avoid timezone issues
    timestamp = datetime.now().timestamp()
    result = format_datetime(timestamp, settings)
    # Should match format YYYY-MM-DD HH:MM:SS
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", result)


def test_format_datetime_iso_hm():
    """Test ISO date format with HH:MM."""
    settings = AppSettings(date_format="YYYY-MM-DD", time_format="HH:MM")
    timestamp = datetime.now().timestamp()
    result = format_datetime(timestamp, settings)
    # Should match format YYYY-MM-DD HH:MM
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", result)


def test_format_datetime_us_format():
    """Test US date format MM/DD/YYYY."""
    settings = AppSettings(date_format="MM/DD/YYYY", time_format="HH:MM:SS")
    timestamp = datetime.now().timestamp()
    result = format_datetime(timestamp, settings)
    # Should match format MM/DD/YYYY HH:MM:SS
    assert re.match(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}", result)


def test_format_datetime_eu_format():
    """Test EU date format DD/MM/YYYY."""
    settings = AppSettings(date_format="DD/MM/YYYY", time_format="HH:MM:SS")
    timestamp = datetime.now().timestamp()
    result = format_datetime(timestamp, settings)
    # Should match format DD/MM/YYYY HH:MM:SS
    assert re.match(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}", result)


def test_format_datetime_zero_timestamp():
    """Test that zero timestamp returns empty string."""
    settings = AppSettings()
    assert format_datetime(0, settings) == ""


def test_format_datetime_negative_timestamp():
    """Test that negative timestamp returns empty string."""
    settings = AppSettings()
    assert format_datetime(-1, settings) == ""


def test_format_datetime_very_large_timestamp():
    """Test very large timestamps (far future)."""
    settings = AppSettings()
    # Year 2500
    timestamp = 16725225600.0
    result = format_datetime(timestamp, settings)
    assert "2500" in result


def test_format_datetime_all_format_combinations():
    """Test all combinations of date and time formats."""
    timestamp = datetime.now().timestamp()
    
    date_formats = ["YYYY-MM-DD", "MM/DD/YYYY", "DD/MM/YYYY"]
    time_formats = ["HH:MM:SS", "HH:MM"]
    
    for date_fmt in date_formats:
        for time_fmt in time_formats:
            settings = AppSettings(date_format=date_fmt, time_format=time_fmt)
            result = format_datetime(timestamp, settings)
            # All should return non-empty formatted strings
            assert result != "", f"Failed for date_format={date_fmt}, time_format={time_fmt}"
            assert len(result) > 5  # At least something like "YYYY-MM-DD HH:MM"


def test_format_datetime_consistency():
    """Test that the same timestamp always formats the same way."""
    timestamp = datetime.now().timestamp()
    settings = AppSettings(date_format="YYYY-MM-DD", time_format="HH:MM:SS")
    
    result1 = format_datetime(timestamp, settings)
    result2 = format_datetime(timestamp, settings)
    
    assert result1 == result2, "Same timestamp should produce same result"
