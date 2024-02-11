import ijson
import time
import logging

from pathlib import Path
from pymongo import MongoClient
from bunnet import init_bunnet

from app import settings

from app.mq import MessageConsumer, MessagePublisher
from app.schemas import UploadedFileMessage, RecordsBatchForProcessing

from app.models import UploadedFile, UploadedFileStatus


class FileSplitterException(Exception):
    pass


class FileSplitter:
    BATCH_SIZE = 100
    EXCHANGE = "veryfi"
    CONSUME_QUEUE = "file_uploaded"
    PUBLISH_QUEUE = "data_processing"

    def __init__(self):
        user = settings.RABBITMQ_USER
        password = settings.RABBITMQ_PASSWORD
        host = settings.RABBITMQ_HOST
        port = settings.RABBITMQ_PORT
        amqp_url = f"amqp://{user}:{password}@{host}:{port}/%2F"

        self.consumer = MessageConsumer(
            amqp_url,
            FileSplitter.CONSUME_QUEUE,
            FileSplitter.EXCHANGE,
            self.message_consumer,
        )

        self.publisher = MessagePublisher(amqp_url, "file_splitter")

        client = MongoClient(settings.MONGODB_CONNECTION_URL)
        init_bunnet(database=client["veryfi"], document_models=[UploadedFile])

        self.logger = logging.getLogger("file_splitter")

    def connect_publisher(self):
        self.publisher.connect()

    def message_consumer(self, body, basic_deliver, properties):
        self.split_uploaded_files_and_send_records_to_processing(body)

    def split_uploaded_files_and_send_records_to_processing(self, message_body):
        """
        This is the core method of the FileSplitter. It gets the uploaded file from storage and reads it, in chunks.
        It then extracts records from the file and sends them in batches
        to data processor service, so they can be processed and saved to the database.
        If everything went well it deletes the uploaded file.

        """

        # TODO: remove time.time and print()
        start = time.time()
        uploaded_file_message = UploadedFileMessage.model_validate_json(message_body)

        file_should_be_deleted = True
        try:
            self.update_file_status(
                uploaded_file_message.id, UploadedFileStatus.processing
            )

            total_records = self.extract_records_and_send_them_to_processing(
                uploaded_file_message
            )

            self.update_number_of_records(uploaded_file_message.id, total_records)

        except ijson.common.IncompleteJSONError as e:
            self.update_file_status(
                uploaded_file_message.id, UploadedFileStatus.failed, raise_exc=False
            )
            self.logger.warning(
                f"Uploaded file did not contain valid json - {uploaded_file_message.id}."
            )
            file_should_be_deleted = False

        except Exception as e:
            self.update_file_status(
                uploaded_file_message.id, UploadedFileStatus.failed, raise_exc=False
            )

            self.logger.error(
                f"Error while processing file {uploaded_file_message.id}."
            )

            raise e

        if file_should_be_deleted:
            self.delete_file(uploaded_file_message.location)

        print("TIME: ", time.time() - start)

    def update_file_status(self, uploaded_file_id, status, raise_exc=True):
        uploaded_file = UploadedFile.get(uploaded_file_id).run()

        if not uploaded_file:
            msg = f"UploadedFile record with id {uploaded_file_id} not found."
            self.logger.error(msg)

            if raise_exc:
                raise FileSplitterException(msg)

            return

        uploaded_file.status = status
        uploaded_file.save()

    def extract_records_and_send_them_to_processing(self, uploaded_file_message):
        total_records = 0
        batch = []

        with open(uploaded_file_message.location, "rb") as file:
            for record in ijson.items(file, "item"):
                batch.append(record)
                total_records += 1

                if len(batch) == FileSplitter.BATCH_SIZE:
                    self.publish_batch_for_processing(batch, uploaded_file_message.id)

                    batch = []

        # Publish leftover records.
        self.publish_batch_for_processing(batch, uploaded_file_message.id)

        return total_records

    def publish_batch_for_processing(self, batch, file_id):
        if not batch:
            return

        records_for_processing = RecordsBatchForProcessing(
            file_id=file_id, records=batch
        )
        self.publisher.publish_message(
            records_for_processing.model_dump_json(),
            FileSplitter.EXCHANGE,
            FileSplitter.PUBLISH_QUEUE,
        )

    def update_number_of_records(self, uploaded_file_id, number_of_records):
        uploaded_file = UploadedFile.get(uploaded_file_id).run()

        if not uploaded_file:
            msg = f"UploadedFile record with id {uploaded_file_id} not found when updating number of records."
            self.logger.error(msg)

            return

        uploaded_file.total_records = number_of_records
        uploaded_file.save()

    def delete_file(self, file_location):
        try:
            Path.unlink(file_location)
        except FileNotFoundError as e:
            self.logger.warning(f"File {file_location} already deleted.")

    def run(self):
        self.connect_publisher()
        self.consumer.run()


def main():
    file_splitter = FileSplitter()
    file_splitter.run()


if __name__ == "__main__":
    main()
