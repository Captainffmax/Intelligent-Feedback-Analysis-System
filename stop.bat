@echo off 
title IFAS Stop 
taskkill /FI "WINDOWTITLE eq IFAS Backend*" /T /F >nul 2>&1 
taskkill /FI "WINDOWTITLE eq IFAS Dashboard*" /T /F >nul 2>&1 
taskkill /FI "WINDOWTITLE eq IFAS Student App*" /T /F >nul 2>&1 
echo All IFAS services have been stopped. 
echo (MongoDB is left running as a Windows service.) 
timeout /t 3 >nul 