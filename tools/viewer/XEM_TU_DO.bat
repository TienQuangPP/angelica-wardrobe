@echo off
title Tu do thoi trang - Kiem Linh
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0server.ps1" -Port 8763 -Page tu_do.html
