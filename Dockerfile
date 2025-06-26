FROM python:3.11-slim

WORKDIR /main

COPY requirements.txt ./
COPY .env ./
COPY entrypoint.sh ./

RUN pip install --no-cache-dir psycopg2-binary sqlalchemy alembic httpx
RUN pip3 install -r requirements.txt

COPY app/ app/
COPY db/ db/
COPY models/ models/

EXPOSE 8080

ENV PYTHONPATH=/main