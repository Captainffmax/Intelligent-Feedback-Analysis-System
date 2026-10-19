@echo off
title IFAS - Build the Student App
setlocal

set "ROOT=%~dp0"

echo ======================================================
echo   IFAS - Build the Student App for Production
echo ======================================================
echo.
echo  The app talks to the API using a RELATIVE path, and the
echo  backend serves the compiled files from its own address.
echo  So there is NO machine address to configure here, and one
echo  build works on any network without rebuilding.
echo.

cd /d "%ROOT%frontend-pwa" || (echo [ERROR] frontend-pwa folder not found. & pause & exit /b 1)

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm was not found. Install Node.js from https://nodejs.org
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo Installing dependencies, this takes a few minutes the first time...
  call npm install --no-audit --no-fund || (echo [ERROR] npm install failed. & pause & exit /b 1)
)

REM VITE_API_BASE_URL must stay EMPTY. With no value the app falls back to the
REM relative "/api", which is what makes it network-independent. Setting it to
REM an absolute address bakes one machine's IP into the compiled files forever.
set "VITE_API_BASE_URL="

call npm run build
if errorlevel 1 (
  echo.
  echo [ERROR] The build failed. Read the message above.
  pause
  exit /b 1
)

echo.
echo ------------------------------------------------------
echo  Build complete. Files are in frontend-pwa\dist
echo  The backend serves them, so just run deploy.bat next.
echo ------------------------------------------------------
pause
