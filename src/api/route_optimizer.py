# route_optimizer.py
#
# Placeholder route optimization layer. Real routing can be delegated to
# Jobber Premium or an external routing API in the future.

from typing import Dict, List

from config.settings import ROUTE_OPTIMIZATION_MODE

SUPPORTED_MODES = {"none", "jobber", "external"}


def get_route_optimization_mode() -> str:
    """Return normalized routing mode."""
    mode = (ROUTE_OPTIMIZATION_MODE or "none").lower()
    return mode if mode in SUPPORTED_MODES else "none"


def optimize_visit_order(visits: List[dict], mode: str = None) -> Dict[str, object]:
    """
    Placeholder route optimizer. Returns metadata describing why optimization
    was skipped or not configured yet.
    """
    resolved_mode = (mode or get_route_optimization_mode()).lower()
    if resolved_mode not in SUPPORTED_MODES:
        resolved_mode = "none"

    if resolved_mode == "none":
        return {
            "mode": resolved_mode,
            "optimized": False,
            "reason": "Route optimization disabled",
            "visit_count": len(visits),
        }

    # Without address/geo data, we cannot compute a real route.
    missing_address = any("address" not in v and "address_data" not in v for v in visits)
    if missing_address:
        return {
            "mode": resolved_mode,
            "optimized": False,
            "reason": "Missing address data for routing",
            "visit_count": len(visits),
        }

    return {
        "mode": resolved_mode,
        "optimized": False,
        "reason": "Routing integration not implemented",
        "visit_count": len(visits),
    }

