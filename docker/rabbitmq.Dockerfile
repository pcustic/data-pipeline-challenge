FROM rabbitmq:3-management

COPY ./docker/rabbitmq_definitions.json /tmp/definitions.json

CMD ["rabbitmq-server"]