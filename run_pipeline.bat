@echo off
REM Full Mudah Rent pipeline: scrape ALL states + ALL types -> clean -> load.
REM Double-click to run defaults. Pass args to override, e.g.:
REM   run_pipeline.bat --state selangor
REM   run_pipeline.bat --skip-scrape
cd /d "%~dp0"
python run_pipeline.py %*
pause
