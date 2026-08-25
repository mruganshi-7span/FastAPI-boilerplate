from pydantic import BaseModel, Field


class MediableCreate(BaseModel):
    media_id: int
    mediable_type: str = Field(min_length=1, max_length=50)
    mediable_id: int
    tag: str = Field(min_length=1, max_length=50)
