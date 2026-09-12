@echo off
REM TransiPulse — One-click startup script
REM ===================================================

echo ================================================
echo   TransiPulse — Public Transport Analytics
echo ================================================
echo.

REM Check Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found. Please install Python 3.11+.
    pause
    exit /b 1
)

REM Create virtual environment if needed
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate

REM Install dependencies
echo Installing dependencies...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt >nul 2>&1

REM Download NLTK data
echo Setting up NLTK data...
python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('vader_lexicon', quiet=True)" 2>nul

REM Run seed if database doesn't exist
if not exist "transipulse.db" (
    echo Seeding database with sample data...
    python -m app.data.seed
)

echo.
echo Starting TransiPulse server...
echo Open http://localhost:8000 in your browser
echo Dashboard: http://localhost:8000/static/dashboard.html
echo Commuter Portal: http://localhost:8000/static/commuter.html
echo API Docs: http://localhost:8000/docs
echo.

python -m app.main
