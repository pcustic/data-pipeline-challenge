FROM python:3.11

WORKDIR /veryfi

COPY ../requirements.txt /veryfi/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /veryfi/requirements.txt

COPY ../.env.template /veryfi/app/.env
COPY ../app/api /veryfi/app/api
COPY ../app/__init__.py ../app/models.py ../app/schemas.py ../app/mq.py ../app/settings.py /veryfi/app/

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "80"]