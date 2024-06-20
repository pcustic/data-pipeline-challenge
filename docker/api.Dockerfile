FROM python:3.11

WORKDIR /company

COPY ../requirements.txt /company/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /company/requirements.txt

COPY ../.env.template /company/app/.env
COPY ../app/api /company/app/api
COPY ../app/__init__.py ../app/models.py ../app/schemas.py ../app/mq.py ../app/settings.py /company/app/

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "80"]