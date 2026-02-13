"""
Pydantic schemas for public Plan API.
"""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class PublicPlanResponse(BaseModel):
    """Plan info exposed on the public landing page (no auth required)."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    display_name: str
    price_cents: int
    billing_period: str
    features: Optional[dict[str, Any]]
    sort_order: int
