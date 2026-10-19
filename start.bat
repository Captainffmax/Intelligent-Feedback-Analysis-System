@echo off
title IFAS Launcher
setlocal

set "ROOT=%~dp0"
set "VENVPY=%ROOT%backend\.venv\Scripts\python.exe"

echo ======================================================
echo   Intelligent Feedback Analysis System - Launcher
echo ======================================================
echo.

REM ---- Pre-flight check 1: does the virtual environment exist? ----------
if not exist "%VENVPY%" (
  echo [ERROR] Python virtual environment not found.
  echo         Expected it here: %VENVPY%
  echo.
  echo   Fix it by running these commands in Command Prompt:
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

REM ---- Pre-flight check 2: are the libraries installed? -----------------
"%VENVPY%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] uvicorn is not installed in the virtual environment.
  echo.
  echo   Fix it by running:
  echo       cd /d "%ROOT%backend"
  echo       .venv\Scripts\activate
  echo       python -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

"%VENVPY%" -c "import streamlit" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] streamlit is not installed in the virtual environment.
  echo.
  echo   Fix it by running:
  echo       cd /d "%ROOT%backend"
  echo       .venv\Scripts\activate
  echo       python -m pip install -r ..\admin-dashboard\requirements.txt
  echo.
  pause
  exit /b 1
)

REM ---- Pre-flight check 3: is Node.js available? ------------------------
where npm >nul 2>&1
if errorlevel 1 (
  echo [WARNING] npm was not found, so the student app cannot start.
  echo           Install Node.js from https://nodejs.org and run this again.
  echo           The backend and dashboard will still start.
  echo.
  set "SKIPNODE=1"
)

REM ---- MongoDB ----------------------------------------------------------
echo Making sure MongoDB is running...
net start MongoDB >nul 2>&1
sc query MongoDB | find "RUNNING" >nul 2>&1
if errorlevel 1 (
  echo [WARNING] The MongoDB service does not appear to be running.
  echo           Right-click Command Prompt, choose "Run as administrator",
  echo           then run:  net start MongoDB
  echo.
) else (
  echo   MongoDB is running.
)
echo.

REM ---- 1. Backend -------------------------------------------------------
echo [1/3] Starting the backend (AI models take 1-4 minutes to warm up)...
start "IFAS Backend" cmd /k "cd /d "%ROOT%backend" && "%VENVPY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 20 >nul

REM ---- 2. Admin dashboard ----------------------------------------------
echo [2/3] Starting the admin dashboard...
start "IFAS Dashboard" cmd /k "cd /d "%ROOT%admin-dashboard" && "%VENVPY%" -m streamlit run app.py --server.port 8501"

timeout /t 5 >nul

REM ---- 3. Student app ---------------------------------------------------
if defined SKIPNODE (
  echo [3/3] Skipped the student app - npm is not installed.
) else (
  echo [3/3] Starting the student app...
  start "IFAS Student App" cmd /k "cd /d "%ROOT%frontend-pwa" && npm run dev"
)

echo.
echo ------------------------------------------------------
echo  Dashboard   : http://localhost:8501   admin / ChangeMe!2026
echo  Backend API : http://127.0.0.1:8000/docs
echo  Student App : http://localhost:5173
echo ------------------------------------------------------
echo  Three new windows have opened. Wait until the backend
echo  window says "Application startup complete".
echo  If a window shows an error, read it - do not close it.
echo.
pause