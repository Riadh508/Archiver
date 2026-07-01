@echo off
set PYTHONPATH=%~dp0
powershell -WindowStyle Hidden -NoProfile -Command "Start-Process python -ArgumentList '-m','arch.web' -WindowStyle Hidden"