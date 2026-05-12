#!/usr/bin/env bash
# Start brightbean-studio locally (Mac / Linux)
set -e

CD="$(cd "$(dirname "$0")" && pwd)"
cd "$CD"

if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
elif [ -f venv/bin/activate ]; then
  source venv/bin/activate
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[brightbean] Created .env -- fill in LARK_APP_ID, LARK_APP_SECRET, LARK_WATCH_FOLDER_TOKEN then re-run."
  exit 1
fi

python -c "from playwright.sync_api import sync_playwright" 2>/dev/null || {
  echo "[brightbean] Installing Playwright..."
  pip install playwright
  playwright install chromium
}

python manage.py migrate --run-syncdb

python manage.py shell -c "
from django.contrib.auth import get_user_model
U = get_user_model()
if not U.objects.filter(is_superuser=True).exists():
    U.objects.create_superuser('admin', 'admin@localhost', 'admin')
    print('[brightbean] Admin created: admin / admin')
"

echo "[brightbean] Open http://localhost:8000  (admin: http://localhost:8000/admin)"
trap 'kill 0' EXIT
python manage.py process_tasks &
python manage.py runserver 0.0.0.0:8000
