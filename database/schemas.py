from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from database.models import ListingStatus, QueueStatus


class SellerBase(BaseModel):
    name: str
    username: Optional[str] = None
    rating: Optional[float] = None
    external_id: Optional[str] = None


class SellerCreate(SellerBase):
    pass


class SellerRead(SellerBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SearchBase(BaseModel):
    query: str
    source: str
    location: Optional[str] = None


class SearchCreate(SearchBase):
    pass


class SearchRead(SearchBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ListingBase(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    source: str
    external_id: Optional[str] = None
    url: Optional[str] = None
    category: Optional[str] = None
    flip_score: Optional[float] = None
    keyword_score: Optional[float] = None
    status: ListingStatus = ListingStatus.NEW


class ListingCreate(ListingBase):
    seller_id: Optional[UUID] = None
    search_id: Optional[UUID] = None


class ListingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    source: Optional[str] = None
    external_id: Optional[str] = None
    url: Optional[str] = None
    status: Optional[ListingStatus] = None
    seller_id: Optional[UUID] = None
    search_id: Optional[UUID] = None


class ListingRead(ListingBase):
    id: UUID
    seller_id: Optional[UUID] = None
    search_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImageBase(BaseModel):
    url: str
    caption: Optional[str] = None


class ImageCreate(ImageBase):
    listing_id: Optional[UUID] = None


class ImageRead(ImageBase):
    id: UUID
    listing_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceHistoryBase(BaseModel):
    price: float


class PriceHistoryCreate(PriceHistoryBase):
    listing_id: Optional[UUID] = None


class PriceHistoryRead(PriceHistoryBase):
    id: UUID
    listing_id: Optional[UUID] = None
    observed_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OpportunityBase(BaseModel):
    potential_profit: float
    confidence_score: float
    notes: Optional[str] = None


class OpportunityCreate(OpportunityBase):
    listing_id: Optional[UUID] = None


class OpportunityRead(OpportunityBase):
    id: UUID
    listing_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QueueBase(BaseModel):
    status: QueueStatus = QueueStatus.NEW
    review_notes: Optional[str] = None


class QueueCreate(QueueBase):
    opportunity_id: UUID


class QueueRead(QueueBase):
    id: UUID
    opportunity_id: UUID
    reviewed_at: Optional[datetime] = None
    version: int = 1
    notification_results: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseBase(BaseModel):
    price_paid: float
    notes: Optional[str] = None


class PurchaseCreate(PurchaseBase):
    listing_id: Optional[UUID] = None


class PurchaseRead(PurchaseBase):
    id: UUID
    listing_id: Optional[UUID] = None
    purchased_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


ItemT = TypeVar("ItemT")


class PaginationMetadata(BaseModel):
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    has_more: bool


class PaginatedResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    pagination: PaginationMetadata
