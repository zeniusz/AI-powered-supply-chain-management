@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creating Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto :error
echo.
echo Starting Threadline Operations at http://127.0.0.1:8601 ...
start "" http://127.0.0.1:8601
python server.py
if errorlevel 1 goto :error
goto :eof
:error
echo Setup failed. Check that Python 3.10 or newer is installed and try again.
pause
