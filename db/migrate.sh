#!/bin/bash

# Fail fast if anything goes wrong
set -e

echo "Running Alembidc migrations..."
alembic -c db/alembic.ini upgrade head
echo "Migrations complete."
