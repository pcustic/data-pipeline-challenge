FROM python:3.11

WORKDIR /veryfi

COPY ../requirements.txt /veryfi/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /veryfi/requirements.txt

COPY ../.env.template /veryfi/app/.env
COPY ../app/processing/_init__.py ../app/processing/file_splitter.py /veryfi/app/processing/
COPY ../app/__init__.py ../app/models.py ../app/schemas.py ../app/mq.py ../app/settings.py /veryfi/app/

CMD ["python", "-m", "app.processing.file_splitter"]