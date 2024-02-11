from contextlib import asynccontextmanager
from secrets import token_urlsafe
from datetime import datetime

from fastapi import FastAPI, UploadFile, status, HTTPException, Request
from bunnet import init_bunnet
from aiofiles import open as aopen

from pymongo import MongoClient

from app import settings

from app.models import Product, UploadedFile
from app.schemas import (
    UploadedFileResponse,
    UploadedFileMessage,
    UploadedFileStatus,
    MultipleProducts,
)
from app.mq import MessagePublisher


async def init_db():
    client = MongoClient(settings.MONGODB_CONNECTION_URL)
    init_bunnet(database=client["veryfi"], document_models=[Product, UploadedFile])


async def init_mq():
    user = settings.RABBITMQ_USER
    password = settings.RABBITMQ_PASSWORD
    host = settings.RABBITMQ_HOST
    port = settings.RABBITMQ_PORT
    amqp_url = f"amqp://{user}:{password}@{host}:{port}/%2F"

    mq = MessagePublisher(amqp_url, app_id="veryfi-api")
    mq.connect()

    return mq


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.mq = await init_mq()

    yield

    app.mq.close()


app = FastAPI(
    title="Veryfi Data Pipeline API",
    description="Data pipeline API for ingesting products data into Veryfi system.",
    lifespan=lifespan,
)
app.mq: MessagePublisher


@app.post("/upload", response_model=UploadedFileResponse, tags=["Upload"])
async def upload_dataset_file(file: UploadFile, request: Request):
    """
    Upload json file with the list of products to ingest into Veryfi database.
    """

    current_time = datetime.now()
    current_timestamp = str(int(current_time.timestamp()))

    random_file_name_part = token_urlsafe(16)
    new_file_location = f"{settings.FILES_DIRECTORY}/{current_timestamp}_{random_file_name_part}_{file.filename}"

    # We write uploaded file to a new location in chunks, so we can handle even really large files.
    try:
        async with aopen(new_file_location, "wb") as out_file:
            while content := await file.read(1024 * 1024):
                await out_file.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"There was an error while uploading your file. Please try again.",
        )

    uploaded_file = UploadedFile(
        filename=file.filename,
        location=new_file_location,
        uploaded_at=current_time,
        content_type=file.content_type,
    )
    uploaded_file.insert()

    message = UploadedFileMessage(
        id=str(uploaded_file.id),
        location=uploaded_file.location,
        uploaded_at=current_time,
    )
    app.mq.publish_message(message.model_dump_json(), "veryfi", "file_uploaded")

    uploaded_file_id = str(uploaded_file.id)
    return {
        "message": "File uploaded successfully!",
        "filename": file.filename,
        "file_id": uploaded_file_id,
        "status_url": str(request.url_for("file_status", file_id=uploaded_file_id)),
    }


@app.get("/upload/status/{file_id}", response_model=UploadedFileStatus, tags=["Upload"])
async def file_status(file_id: str):
    """
    Check the status of an uploaded file.
    """

    uploaded_file = UploadedFile.get(file_id).run()

    if not uploaded_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="There is no file with this id",
        )

    return {
        "filename": uploaded_file.filename,
        "status": uploaded_file.status,
        "uploaded_at": uploaded_file.uploaded_at,
        "total_records": uploaded_file.total_records,
        "records_processed": uploaded_file.records_processed,
        "records_failed": uploaded_file.records_failed,
    }


@app.get("/product/find/code/{code}", response_model=Product, tags=["Find Products"])
async def find_product_by_code(code: str):
    """
    Find single product by code.
    """

    product = Product.find_one(Product.code == code).run()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="There is no product with this code.",
        )

    return product


@app.get(
    "/product/find/name/partial/{product_name}",
    response_model=MultipleProducts,
    tags=["Find Products"],
)
async def find_products_partial(product_name: str):
    """
    Find top 20 products that contain product_name in the product_name field.
    """

    regex_pattern = f".*{product_name}.*"

    products = (
        Product.find({"product_name": {"$regex": regex_pattern, "$options": "i"}})
        .limit(20)
        .to_list()
    )

    response = {"search_term": product_name, "products": products}

    return response


@app.get(
    "/product/find/name/exact/{product_name}",
    response_model=MultipleProducts,
    tags=["Find Products"],
)
async def find_products_exact(product_name: str):
    """
    Find products that exactly match the product name. Show at most 20 results.
    """

    products = Product.find(Product.product_name == product_name)

    response = {"search_term": product_name, "products": products}

    return response
