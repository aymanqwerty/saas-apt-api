from pydantic import BaseModel


class MediaUploadData(BaseModel):
    url: str
