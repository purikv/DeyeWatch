@echo off
rem Збірка DeyeWatch.exe (один файл, без консолі). Потрібен Python 3.9+.
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed --name DeyeWatch --icon deyewatch.ico deyewatch.py || exit /b 1
echo.
echo Готово: %~dp0dist\DeyeWatch.exe
