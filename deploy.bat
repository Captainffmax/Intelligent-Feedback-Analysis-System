@echo off
title IFAS Deployment Launcher
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "VENVPY=%ROOT%backend\.venv\Scripts\python.exe"

echo ======================================================
echo   IFAS - Production Launcher
echo ======================================================
echo.

REM ---- Check 1: virtual environment --------------------------------------
if not exist "%VENVPY%" (
  echo [ERROR] Python virtual environment not found.
  echo         Expected it here: %VENVPY%
  echo.
  echo   Create it with:
  echo       cd /d "%ROOT%backend"
  echo       python -m venv .venv
  echo       .venv\Scripts\activate
  echo       python -m pip install -r requirements.txt
  echo       python -m pip install -r ..\admin-dashboard\requirements.txt
  echo       python -m spacy download en_core_web_sm
  echo.
  pause
  exit /b 1
)

REM ---- Check 2: libraries -------------------------------------------------
"%VENVPY%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] uvicorn is not installed in the virtual environment.
  echo         Run: python -m pip install -r backend\requirements.txt
  pause
  exit /b 1
)
"%VENVPY%" -c "import streamlit" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] streamlit is not installed in the virtual environment.
  echo         Run: python -m pip install -r admin-dashboard\requirements.txt
  pause
  exit /b 1
)

REM ---- Check 3: the student app has been built ----------------------------
if not exist "%ROOT%frontend-pwa\dist\index.html" (
  echo [ERROR] The student app has not been built yet.
  echo         Run build-frontend.bat first, then run this file again.
  echo.
  pause
  exit /b 1
)

REM ---- Check 4: MongoDB ---------------------------------------------------
echo Making sure MongoDB is running...
net start MongoDB >nul 2>&1
sc query MongoDB | find "RUNNING" >nul 2>&1
if errorlevel 1 (
  echo [WARNING] The MongoDB service does not appear to be running.
  echo           Close this window, right-click deploy.bat and choose
  echo           "Run as administrator", then try again.
  echo.
) else (
  echo   MongoDB is running.
)
echo.

REM ---- Find this machine's address ----------------------------------------
set "SUGGEST="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
  set "CAND=%%a"
  set "CAND=!CAND: =!"
  if "!SUGGEST!"=="" set "SUGGEST=!CAND!"
)
if "%SUGGEST%"=="" set "SUGGEST=127.0.0.1"

REM ---- 1. Backend — serves BOTH the API and the student app ---------------
echo [1/2] Starting the backend (AI models take 1-4 minutes to warm up)...
start "IFAS Backend" cmd /k "cd /d "%ROOT%backend" && "%VENVPY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

timeout /t 25 >nul

REM ---- 2. Admin dashboard -------------------------------------------------
echo [2/2] Starting the admin dashboard...
start "IFAS Dashboard" cmd /k "cd /d "%ROOT%admin-dashboard" && "%VENVPY%" -m streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true"

echo.
echo ------------------------------------------------------
echo  Students open : http://%SUGGEST%:8000
echo  Dashboard     : http://%SUGGEST%:8501
echo  API docs      : http://%SUGGEST%:8000/docs
echo ------------------------------------------------------
echo  The backend serves the student app itself, so there is
echo  no separate app server and no address to rebuild when
echo  the network changes.
echo.
echo  Wait until the backend window says
echo  "Application startup complete" before testing.
echo.
echo  If phones cannot reach these addresses, allow ports
echo  8000 and 8501 through the Windows Firewall.
echo.
pause
