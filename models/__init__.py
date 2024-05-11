from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl
from pydantic import field_validator


class EventSource(Enum):
    KUDAGO = 'KUDAGO'
    TIMEPAD = 'TIMEPAD'
    NETWORKLY = 'NETWORKLY'
    RESONANSE = 'RESONANSE'


class Venue(BaseModel):
    title: str | None = None
    address: str | None = None
    lat: float | None = None
    lon: float | None = None


class Image(BaseModel):
    image_url: HttpUrl | None = None
    local_image: str | None = None

    @field_validator('image_url', mode='before')
    def set_default_image_url(cls, value):
        try:
            return HttpUrl(url=value)
        except ValueError:
            return None


class Price(BaseModel):
    price: float
    currency: str


class BasicEvent(BaseModel):
    id: UUID
    title: str
    datetime_from: datetime
    description: str | None = None
    datetime_to: Optional[datetime] = None
    city: str
    venue: Venue
    picture: Image
    price: Price | None = None
    tags: list[str] = Field(default_factory=list)
    contact: str | None = None


class EventData(BasicEvent):
    service_type: EventSource
    service_data: dict  # custom service data


class ResonanceEventInfo(BaseModel):
    subject: int
    creator_id: int
    contact_info: Optional[str] = Field(None, max_length=255)
    creation_time: datetime = Field(default_factory=datetime.now)

# other
#
# class KudaGoEvent(BaseModel):
#     id: int
#     publication_date: int
#     dates: list[Date]
#     title: str
#     slug: str
#     place: Place
#     description: str
#     body_text: str
#     location: Location
#     categories: list[str]
#     tagline: str
#     age_restriction: str
#     price: str
#     is_free: bool
#     images: list[Image]
#     favorites_count: int
#     comments_count: int
#     site_url: HttpUrl
#     short_title: str
#     tags: list[str]
#     disable_comments: bool
#     participants: list[Participant]
