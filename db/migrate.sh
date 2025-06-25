#!/bin/bash

# Fail fast if anything goes wrong
echo "Running Alembic migrations..."
alembic -c db/alembic.ini upgrade head
echo "Migrations complete."
