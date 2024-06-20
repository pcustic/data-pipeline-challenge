import logging

from datetime import datetime

from pydantic import ValidationError
from pymongo import MongoClient, UpdateOne
from bunnet import init_bunnet

from app import settings

from app.mq import MessageConsumer
from app.schemas import RecordsBatchForProcessing
from app.models import Product, UploadedFile, UploadedFileStatus


class DataProcessor:
    EXCHANGE = "company"
    CONSUME_QUEUE = "data_processing"

    def __init__(self):
        user = settings.RABBITMQ_USER
        password = settings.RABBITMQ_PASSWORD
        host = settings.RABBITMQ_HOST
        port = settings.RABBITMQ_PORT
        amqp_url = f"amqp://{user}:{password}@{host}:{port}/%2F"

        self.consumer = MessageConsumer(
            amqp_url,
            DataProcessor.CONSUME_QUEUE,
            DataProcessor.EXCHANGE,
            self.message_consumer,
        )

        client = MongoClient(settings.MONGODB_CONNECTION_URL)
        init_bunnet(database=client["company"], document_models=[Product, UploadedFile])
        self.product_collection = Product.get_motor_collection()

        self.logger = logging.getLogger("data_processor")

    def message_consumer(self, body, basic_deliver, properties):
        # This method is called on every message by the MessageConsumer - RabbitMQ consumer client.
        self.process_records_and_store_them_to_database(body)

    def process_records_and_store_them_to_database(self, message_body):
        """
        This is the core method of the DataProcessor. It gets the records from the message, prepares them for insertion
        to the database and then does the upsert (update if there already exists record with the same id,
        insert otherwise).

        """
        records_batch = RecordsBatchForProcessing.model_validate_json(message_body)

        records_processed = 0
        records_failed = 0

        batch_for_insert = []
        for record in records_batch.records:
            record = self.prepeare_record(record, records_batch)

            try:
                product_record = Product.model_validate(record)
            except ValidationError as e:
                code = record["code"] if "code" in record else "MISSING"

                self.logger.warning(
                    f"Could not process record with code {code} - file_id {records_batch.file_id}"
                )
                records_failed += 1

                continue

            batch_for_insert.append(product_record)
            records_processed += 1

        if batch_for_insert:
            self.upsert_batch(batch_for_insert)

        self.update_uploaded_file_records_number_data(
            records_batch.file_id, records_processed, records_failed
        )

    def prepeare_record(self, record, records_batch):
        # We need to remove the external ids if they exist and add our file_id and last_modified_at_company.
        if "id" in record:
            del record["id"]

        if "_id" in record:
            del record["_id"]

        record["file_id"] = records_batch.file_id
        record["last_modified_at_company"] = datetime.now()

        return record

    def upsert_batch(self, products):
        """
        There is no batch upsert method in Bunnet ODM, so we use pymongo directly to make upsert more efficient.
        This gives us 10x performance improvement over multiple single item upserts using bunnet ODM.
        """

        products_to_upsert = []
        for product in products:
            product_dict = product.model_dump()

            products_to_upsert.append(
                UpdateOne(
                    {"code": product.code},
                    {"$set": product_dict},
                    upsert=True,
                )
            )

        self.product_collection.bulk_write(products_to_upsert)

    def update_uploaded_file_records_number_data(
        self, uploaded_file_id, records_processed, records_failed
    ):
        # Since there might be multiple workers updating these values we must do it this way in a single operation.
        UploadedFile.get(uploaded_file_id).inc(
            {
                UploadedFile.records_processed: records_processed,
                UploadedFile.records_failed: records_failed,
            }
        ).run()

        # If we have processed all records from a file we will update the status of the UploadedFile record.
        # That way the status API will have up-to-date information about the uploaded file.
        uploaded_file = UploadedFile.get(uploaded_file_id).run()
        total_processed_records = (
            uploaded_file.records_processed + uploaded_file.records_failed
        )

        if total_processed_records < uploaded_file.total_records:
            return

        status = UploadedFileStatus.processed
        if uploaded_file.records_failed > 0:
            status = UploadedFileStatus.processed_with_errors

        uploaded_file.status = status
        uploaded_file.save()

    def run(self):
        self.consumer.run()


def main():
    data_processor = DataProcessor()
    data_processor.run()


if __name__ == "__main__":
    main()
