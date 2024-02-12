from datetime import datetime
from enum import Enum

from bunnet import Document, Indexed, before_event, Insert, Replace


class Product(Document):
    code: Indexed(str, unique=True)
    product_name: str | None = None

    last_modified_at_veryfi: datetime | None = None
    # file_id is here we know from which file it was imported.
    file_id: str

    class Config:
        extra = "allow"

    class Settings:
        name = "products"
        indexes = ["product_name"]

    @before_event(Insert, Replace)
    def update_last_modified(self):
        self.last_modified_at_veryfi = datetime.now()


class UploadedFileStatus(str, Enum):
    uploaded = "uploaded - waiting for processing"
    processing = "processing"
    failed = "failed"
    processed = "processed"
    processed_with_errors = "processed_with_errors"


class UploadedFile(Document):
    filename: str
    location: str
    uploaded_at: datetime
    content_type: str
    status: UploadedFileStatus = UploadedFileStatus.uploaded

    total_records: int = 0
    records_processed: int = 0
    records_failed: int = 0

    class Settings:
        name = "uploaded_files"
