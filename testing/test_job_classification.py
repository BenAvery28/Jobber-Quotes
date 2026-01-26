# testing/test_job_classification.py
"""
Tests for job classification (commercial vs residential).
"""

import os
import pytest
from datetime import datetime

# Set required environment variables before importing
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("JOBBER_API_BASE", "https://api.getjobber.com/api")
os.environ.setdefault("TEST_MODE", "True")

from src.api.job_classifier import classify_job_tag, get_crew_for_tag


def test_commercial_address_keywords():
    """Test that commercial addresses are correctly identified."""
    test_cases = [
        ("123 Main Street, Suite 200", "commercial"),
        ("Downtown Plaza, Saskatoon", "commercial"),
        ("Office Tower Building", "commercial"),
        ("Shopping Center", "commercial"),
        ("Industrial Complex", "commercial"),
        ("123 Business Ave", "commercial"),
    ]
    
    for address, expected_tag in test_cases:
        tag = classify_job_tag(address=address)
        assert tag == expected_tag, f"Address '{address}' should be classified as {expected_tag}, got {tag}"


def test_residential_address_keywords():
    """Test that residential addresses are correctly identified."""
    test_cases = [
        ("123 Home Street", "residential"),
        ("Residential Apartment", "residential"),
        ("Condo Unit 5", "residential"),
        ("Townhouse Complex", "residential"),
        ("123 House Lane", "residential"),
    ]
    
    for address, expected_tag in test_cases:
        tag = classify_job_tag(address=address)
        assert tag == expected_tag, f"Address '{address}' should be classified as {expected_tag}, got {tag}"


def test_suite_unit_numbers():
    """Test that suite/unit numbers indicate commercial."""
    test_cases = [
        ("123 Main St, Suite 100", "commercial"),
        ("Building A, Unit 5", "commercial"),
        ("Floor 3, Office 301", "commercial"),
        ("#200", "commercial"),
    ]
    
    for address, expected_tag in test_cases:
        tag = classify_job_tag(address=address)
        assert tag == expected_tag, f"Address '{address}' should be classified as {expected_tag}, got {tag}"


def test_high_value_quotes():
    """Test that high-value quotes (>$1000) lean commercial."""
    # High value without clear address
    tag = classify_job_tag(address="123 Unknown", quote_amount=1500)
    assert tag == "commercial", f"High-value quote should be commercial, got {tag}"
    
    # Low value should default to residential
    tag = classify_job_tag(address="123 Unknown", quote_amount=500)
    assert tag == "residential", f"Low-value quote should be residential, got {tag}"


def test_client_name_classification():
    """Test that client names can influence classification."""
    # Commercial company name
    tag = classify_job_tag(address="", client_name="ABC Corporation")
    assert tag == "commercial", f"Corporation name should be commercial, got {tag}"
    
    # Residential name
    tag = classify_job_tag(address="", client_name="John's Home")
    assert tag == "residential", f"Home name should be residential, got {tag}"


def test_combined_indicators():
    """Test classification with multiple indicators."""
    # Strong commercial indicators
    tag = classify_job_tag(
        address="123 Business Plaza, Suite 200",
        client_name="ABC Corp",
        quote_amount=2000
    )
    assert tag == "commercial", "Multiple commercial indicators should result in commercial"
    
    # Strong residential indicators
    tag = classify_job_tag(
        address="123 Home Street",
        client_name="Residential Apartment",
        quote_amount=500
    )
    assert tag == "residential", "Multiple residential indicators should result in residential"


def test_default_residential():
    """Test that unclear cases default to residential."""
    # No information
    tag = classify_job_tag()
    assert tag == "residential", f"Empty input should default to residential, got {tag}"
    
    # Ambiguous address
    tag = classify_job_tag(address="123 Main St")
    assert tag == "residential", f"Ambiguous address should default to residential, got {tag}"


def test_get_crew_for_tag():
    """Test crew assignment based on job tag."""
    assert get_crew_for_tag("commercial") == "commercial_crew"
    assert get_crew_for_tag("residential") == "residential_crew"
    assert get_crew_for_tag("unknown") == "residential_crew"  # Default


def test_edge_cases():
    """Test edge cases in classification."""
    # Empty strings
    tag = classify_job_tag(address="", client_name="", quote_amount=None)
    assert tag == "residential"
    
    # Very long address
    long_address = "123 " + "Business " * 20 + "Street"
    tag = classify_job_tag(address=long_address)
    assert tag == "commercial"
    
    # Mixed case
    tag = classify_job_tag(address="OFFICE BUILDING")
    assert tag == "commercial"
    
    tag = classify_job_tag(address="residential home")
    assert tag == "residential"

