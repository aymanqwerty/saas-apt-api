import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.service import ServiceStatus


class ServiceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    image_url: str | None = None
    sort_order: int = Field(default=0, ge=0)
    status: ServiceStatus = ServiceStatus.ACTIVE


class ServiceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    image_url: str | None = None
    sort_order: int | None = Field(default=None, ge=0)
    status: ServiceStatus | None = None


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    image_url: str | None
    sort_order: int
    status: ServiceStatus
