set -e

echo "Running Alembidc migrations..."
alembic -c db/alembic.ini upgrade head
echo "Migrations complete."

python3 ./app/main.py