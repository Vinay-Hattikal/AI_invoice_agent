@echo off
echo ==================================================
echo   AI Automation Agent Pipeline - Setup & Run
echo ==================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.10+ and try again.
    pause
    exit /b 1
)

REM Set up virtual environment if it doesn't exist
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM Install dependencies
echo Installing requirements...
call .\venv\Scripts\pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

REM Run the pipeline script
echo.
echo Running the pipeline on sample documents...
.\venv\Scripts\python.exe pipeline.py
if %errorlevel% neq 0 (
    echo [ERROR] Pipeline execution failed.
    pause
    exit /b 1
)

echo.
echo ==================================================
echo   Execution Finished Successfully!
echo   Output folders located in: sample_output/
echo ==================================================
echo.
pause
