@echo off
REM Start brightbean-studio locally (Windows)
cd /d "%~dp0"

IF EXIST .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) ELSE (
  IF EXIST venv\Scripts\activate.bat call venv\Scripts\activate.bat
)

IF NOT EXIST .env (
  copy .env.example .env
  echo [brightbean] Created .env -- fill in LARK_APP_ID, LARK_APP_SECRET, LARK_WATCH_FOLDER_TOKEN then re-run.
  pause & exit /b 1
)

python -c "from playwright.sync_api import sync_playwright" 2>nul
IF ERRORLEVEL 1 (
  echo [brightbean] Installing Playwright...
  pip install playwright
  playwright install chromium
)

python manage.py migrate --run-syncdb
python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); U.objects.filter(is_superuser=True).exists() or U.objects.create_superuser('admin','admin@localhost','admin')"

echo [brightbean] Open http://localhost:8000  (admin: http://localhost:8000/admin)
start "brightbean-worker" cmd /k "python manage.py process_tasks"
python manage.py runserver 0.0.0.0:8000
pause
