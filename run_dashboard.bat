@echo off
echo ==================================================
echo   AI Automation Agent - Launching Web Dashboard
echo ==================================================
echo.

REM Verify virtual environment exists
if not exist venv (
    echo [WARNING] Python virtual environment 'venv' was not found.
    echo Running setup first...
    call run_pipeline.bat
)

REM Open default browser to local URL
echo Opening web dashboard in your browser...
start http://localhost:8000

REM Start the server using virtual environment python
echo Starting local HTTP server on port 8000...
.\venv\Scripts\python.exe server.py
if %errorlevel% neq 0 (
    echo [ERROR] Web server stopped or failed to launch.
    pause
    exit /b 1
)
