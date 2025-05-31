FROM python:3.11-slim

COPY ./requirements.txt /requirements.txt
RUN pip install --no-cache-dir psycopg2-binary sqlalchemy alembic
RUN pip3 install -r requirements.txt

COPY . /app/
WORKDIR /app