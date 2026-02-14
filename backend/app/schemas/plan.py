"""
Pydantic schemas for public Plan API.
"""
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PublicPlanResponse(BaseModel):
    """Plan info exposed on the public landing page (no auth required)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str
    price_cents: int
    billing_period: str
    upload_limit_daily: int
    max_file_size_mb: int
    max_conversations_daily: int
    max_tokens_daily: int
    features: Optional[dict[str, Any]]
    sort_order: int
    is_purchasable: bool = False
