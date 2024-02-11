from pydantic import BaseModel
from datetime import datetime

from .models import Product


class UploadedFileResponse(BaseModel):
    """
    Response of a file upload API.
    """

    message: str
    filename: str
    file_id: str
    status_url: str


class UploadedFileStatus(BaseModel):
    """
    Response of a file status API
    """

    filename: str
    status: str
    uploaded_at: datetime

    total_records: int
    records_processed: int
    records_failed: int


class UploadedFileMessage(BaseModel):
    """
    Message for RabbitMQ that a new file was uploaded.
    """

    id: str
    location: str
    uploaded_at: datetime


class RecordsBatchForProcessing(BaseModel):
    """
    Message that contains records for processing from an uploaded file.
    """

    file_id: str
    records: list[dict]


class MultipleProducts(BaseModel):
    products: list[Product]
