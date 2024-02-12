import os
from dotenv import load_dotenv

# load environment variables from .env
load_dotenv()


MONGODB_CONNECTION_URL = os.getenv(
    "MONGODB_CONNECTION_URL", "mongodb://localhost:27017/veryfi"
)

RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))

FILES_DIRECTORY = os.getenv(
    "FILES_DIRECTORY",
    "/data/uploaded_files",
)
