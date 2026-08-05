from pydantic import BaseModel, Field


class QueueEnqueueItem(BaseModel):
    job_id: str | None = None
    version_id: str | None = None
    source_url: str | None = None
    company: str | None = None
    position: str | None = None


class QueueEnqueueRequest(BaseModel):
    user_id: str
    items: list[QueueEnqueueItem] = Field(default_factory=list)


class QueueItemResponse(BaseModel):
    id: str
    user_id: str
    job_id: str | None = None
    version_id: str | None = None
    source_url: str | None = None
    company: str | None = None
    position: str | None = None
    fill_status: str
    awaiting_confirm: bool = False
    apply_id: str | None = None
    submitted_at: str | None = None
    skipped_at: str | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class QueueListResponse(BaseModel):
    items: list[QueueItemResponse]


class QueueAckRequest(BaseModel):
    user_id: str
    acknowledge: bool = False
