@echo off
rem Double-click to open the app, or drag an academic balance (maazan) PDF onto this file.
cd /d "%~dp0"
start "" pyw "src\app\maazan_app.py" %*
