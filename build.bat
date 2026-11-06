@echo off
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m pip install --disable-pip-version-check -r requirements.txt
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name TcpSocketTool --distpath dist --workpath build --specpath build app.py
copy /Y dist\TcpSocketTool.exe TcpSocketTool.exe
echo.
echo EXE: %cd%\TcpSocketTool.exe
