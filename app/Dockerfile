FROM python:3.11-slim

COPY . /app/

WORKDIR /app

RUN pip install --no-cache-dir psycopg2-binary sqlalchemy alembic

RUN pip3 install -r requirements.txt