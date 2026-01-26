# job_classifier.py
#
# Classifies jobs as commercial or residential based on address and other factors.
# Can be extended with intelligent lookup services in the future.

import re
from typing import Optional


# Commercial indicators in addresses (more specific terms)
COMMERCIAL_KEYWORDS = [
    "plaza", "mall", "shopping", "center", "centre", "office", "building",
    "tower", "complex", "suite", "floor", "inc", "ltd", "corp",
    "corporation", "company", "business", "enterprise", "industrial", "warehouse"
]

# Residential indicators
RESIDENTIAL_KEYWORDS = [
    "house", "home", "residence", "residential", "apartment", "apt", "condo",
    "condominium", "townhouse", "townhouse", "villa", "cottage", "bungalow"
]


def classify_job_tag(address: Optional[str] = None, client_name: Optional[str] = None, 
                     quote_amount: Optional[float] = None) -> str:
    """
    Classify a job as 'commercial' or 'residential' based on available information.
    
    Args:
        address: Job address (primary indicator)
        client_name: Client name (secondary indicator)
        quote_amount: Quote amount (tertiary indicator - commercial jobs often higher)
    
    Returns:
        str: 'commercial' or 'residential' (defaults to 'residential' if unclear)
    """
    address_lower = (address or "").lower()
    client_lower = (client_name or "").lower()
    
    # Check address for commercial indicators
    commercial_score = 0
    residential_score = 0
    
    # Address-based classification
    for keyword in COMMERCIAL_KEYWORDS:
        if keyword in address_lower:
            commercial_score += 2
    
    for keyword in RESIDENTIAL_KEYWORDS:
        if keyword in address_lower:
            residential_score += 2
    
    # Client name-based classification
    for keyword in COMMERCIAL_KEYWORDS:
        if keyword in client_lower:
            commercial_score += 1
    
    for keyword in RESIDENTIAL_KEYWORDS:
        if keyword in client_lower:
            residential_score += 1
    
    # Quote amount heuristic (commercial jobs often $1000+)
    if quote_amount and quote_amount >= 1000:
        commercial_score += 1
    
    # Check for suite/unit numbers (common in commercial)
    # Look for "Suite", "Unit", "Floor", "#" followed by numbers
    if re.search(r'\b(suite|unit|floor)\s*\d+', address_lower, re.IGNORECASE):
        commercial_score += 2  # Strong indicator
    if re.search(r'#\s*\d+', address_lower):
        commercial_score += 1
    
    # Decision logic
    if commercial_score > residential_score:
        return "commercial"
    elif residential_score > commercial_score:
        return "residential"
    else:
        # Default to residential if unclear (safer default)
        return "residential"


def get_crew_for_tag(job_tag: str) -> str:
    """
    Get the crew assignment for a job tag.
    
    Args:
        job_tag: 'commercial' or 'residential'
    
    Returns:
        str: Crew identifier ('commercial_crew' or 'residential_crew')
    """
    if job_tag == "commercial":
        return "commercial_crew"
    elif job_tag == "residential":
        return "residential_crew"
    else:
        return "residential_crew"  # Default crew

