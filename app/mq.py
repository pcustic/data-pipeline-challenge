import logging
import pika

from pika.adapters.asyncio_connection import AsyncioConnection


logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
logger = logging.getLogger(__name__)

# Reduce the log level of pika client to WARNING, so we don't overfill the logs.
logging.getLogger("pika").setLevel(logging.WARNING)


class RabbitMQException(Exception):
    pass


class MessagePublisher:
    """Class to make it easier to publish messages to RabbitMQ"""

    def __init__(self, amqp_url: str, app_id: str):
        self._connection = None
        self._channel = None

        self._url = amqp_url

        self._properties = pika.BasicProperties(
            app_id=app_id, content_type="application/json"
        )

    def connect(self):
        return AsyncioConnection(
            pika.URLParameters(self._url),
            on_open_callback=self.on_connection_open,
            on_open_error_callback=self.on_connection_open_error,
            on_close_callback=self.on_connection_closed,
        )

    def on_connection_open(self, connection):
        self._connection = connection
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_connection_open_error(self, _unused_connection, err):
        logger.error("Connection open failed: %s", err)

    def on_connection_closed(self, _unused_connection, reason):
        logger.warning("Connection closed: %s", reason)
        self._channel = None

    def on_channel_open(self, channel):
        self._channel = channel
        self.add_on_channel_close_callback()

    def add_on_channel_close_callback(self):
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reason):
        self._channel = None

    def publish_message(self, message, exchange, routing_key):
        if self._channel is None or not self._channel.is_open:
            raise RabbitMQException("Channel closed.")

        self._channel.basic_publish(
            exchange,
            routing_key,
            message,
            self._properties,
        )

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None


class MessageConsumer:
    """Class to make it easier to consume messages from RabbitMQ"""

    def __init__(self, amqp_url, queue, exchange, consumer_method):
        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._url = amqp_url
        self._queue = queue
        self._exchange = exchange
        self._consuming = False

        self._consume_message = consumer_method

        self._prefetch_count = 1

    def connect(self):
        return AsyncioConnection(
            parameters=pika.URLParameters(self._url),
            on_open_callback=self.on_connection_open,
            on_open_error_callback=self.on_connection_open_error,
            on_close_callback=self.on_connection_closed,
        )

    def close_connection(self):
        self._consuming = False
        if self._connection:
            self._connection.close()

    def on_connection_open(self, _unused_connection):
        self.open_channel()

    def on_connection_open_error(self, _unused_connection, err):
        logger.error("Connection open failed: %s", err)

    def on_connection_closed(self, _unused_connection, reason):
        self._channel = None
        if self._closing:
            self._connection.ioloop.stop()

    def open_channel(self):
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):
        self._channel = channel
        self.add_on_channel_close_callback()
        self.setup_queue(self._queue)

    def add_on_channel_close_callback(self):
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reason):
        self.close_connection()

    def setup_queue(self, queue_name):
        self._channel.queue_bind(self._queue, self._exchange, callback=self.on_bindok)

    def on_bindok(self, _unused_frame):
        self.set_qos()

    def set_qos(self):
        self._channel.basic_qos(
            prefetch_count=self._prefetch_count, callback=self.on_basic_qos_ok
        )

    def on_basic_qos_ok(self, _unused_frame):
        self.start_consuming()

    def start_consuming(self):
        self.add_on_cancel_callback()
        self._consumer_tag = self._channel.basic_consume(self._queue, self.on_message)
        self._consuming = True

    def add_on_cancel_callback(self):
        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)

    def on_consumer_cancelled(self, method_frame):
        if self._channel:
            self._channel.close()

    def on_message(self, _unused_channel, basic_deliver, properties, body):
        """
        Invoked by pika when a message is delivered from RabbitMQ.
        It calls the _consume_message method that was passed on creation of the MessageConsumer object.

        If there is an unhandled error while processing it redelivers the message.
        """
        try:
            self._consume_message(body, basic_deliver, properties)
        except Exception as e:
            self.redeliver_message(basic_deliver.delivery_tag)
            return

        self.acknowledge_message(basic_deliver.delivery_tag)

    def acknowledge_message(self, delivery_tag):
        self._channel.basic_ack(delivery_tag)

    def redeliver_message(self, delivery_tag):
        self._channel.basic_nack(delivery_tag)

    def stop_consuming(self):
        if self._channel:
            self._channel.basic_cancel(self._consumer_tag, self.on_cancelok)

    def on_cancelok(self, _unused_frame):
        self._consuming = False
        self.close_channel()

    def close_channel(self):
        self._channel.close()

    def run(self):
        self._connection = self.connect()
        self._connection.ioloop.run_forever()

    def stop(self):
        if not self._closing:
            self._closing = True
            if self._consuming:
                self.stop_consuming()
                self._connection.ioloop.run_forever()
            else:
                self._connection.ioloop.stop()
