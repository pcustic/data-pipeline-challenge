FROM python:3.11

WORKDIR /company

COPY ../requirements.txt /company/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /company/requirements.txt

COPY ../.env.template /company/app/.env
COPY ../app/processing/_init__.py ../app/processing/data_processor.py /company/app/processing/
COPY ../app/__init__.py ../app/models.py ../app/schemas.py ../app/mq.py ../app/settings.py /company/app/

CMD ["python", "-m", "app.processing.data_processor"]