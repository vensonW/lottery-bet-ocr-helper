@echo off
cd /d "%~dp0"
setlocal

set APP_NAME=lottery-bet-ocr-helper
set UV_CACHE_DIR=%CD%\.uv_cache
set UV_LOCK_TIMEOUT=1800
if "%UV_DEFAULT_INDEX%"=="" set UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

where uv >nul 2>nul
if errorlevel 1 goto BUILD_WITH_PIP

echo Building desktop exe: %APP_NAME%
echo This may take a long time on the first run because PySide6-Essentials and PyInstaller are large.
echo Note: package download progress is printed by uv, for example: xx MiB/xx MiB.
echo PyPI index: %UV_DEFAULT_INDEX%
echo.

echo [1/5] Preparing dependencies...
uv run ^
  --with openai ^
  --with Pillow ^
  --with openpyxl ^
  --with PySide6-Essentials ^
  --with pyinstaller ^
  python -c "print('dependencies ready')"
if errorlevel 1 goto BUILD_FAILED

echo.
echo [2/5] Cleaning old build files...
if exist "build" rmdir /s /q "build"
if exist "dist\%APP_NAME%" rmdir /s /q "dist\%APP_NAME%"
if exist "%APP_NAME%.spec" del /f /q "%APP_NAME%.spec"

echo.
echo [3/5] Running PyInstaller...
uv run ^
  --with-requirements requirements-build.txt ^
  pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "%APP_NAME%" ^
  --paths "%CD%\src" ^
  --add-data "skills;skills" ^
  --hidden-import api_test ^
  --hidden-import mock_openai_client ^
  --hidden-import openai ^
  --hidden-import httpx ^
  --hidden-import httpcore ^
  --hidden-import anyio ^
  --hidden-import certifi ^
  --hidden-import distro ^
  --hidden-import jiter ^
  --hidden-import sniffio ^
  --hidden-import openpyxl.cell._writer ^
  --collect-submodules openai ^
  --collect-submodules httpx ^
  --collect-submodules httpcore ^
  --collect-submodules anyio ^
  --collect-data certifi ^
  app.py

if errorlevel 1 goto BUILD_FAILED

echo.
echo [4/5] Copying support files...
copy /Y "config.example.ini" "dist\%APP_NAME%\config.example.ini" >nul
copy /Y "README.md" "dist\%APP_NAME%\README.md" >nul

echo.
echo [5/5] Creating zip package...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\zip_dist.ps1" -SourceDir "dist\%APP_NAME%" -DestinationZip "dist\%APP_NAME%.zip" -Retries 6 -DelaySeconds 5
if errorlevel 1 goto ZIP_FAILED

echo.
echo Build finished.
echo EXE: dist\%APP_NAME%\%APP_NAME%.exe
echo ZIP: dist\%APP_NAME%.zip
pause
exit /b 0

:BUILD_FAILED
echo.
echo Build failed.
pause
exit /b 1

:BUILD_WITH_PIP
echo Building desktop exe without uv: %APP_NAME%
echo uv was not found. Falling back to python -m pip and python -m PyInstaller.
echo.

where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON

echo [1/5] Installing build dependencies...
python -m pip install -r requirements-build.txt
if errorlevel 1 goto BUILD_FAILED

echo.
echo [2/5] Cleaning old build files...
if exist "build" rmdir /s /q "build"
if exist "dist\%APP_NAME%" rmdir /s /q "dist\%APP_NAME%"
if exist "%APP_NAME%.spec" del /f /q "%APP_NAME%.spec"

echo.
echo [3/5] Running PyInstaller...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "%APP_NAME%" ^
  --paths "%CD%\src" ^
  --add-data "skills;skills" ^
  --hidden-import api_test ^
  --hidden-import mock_openai_client ^
  --hidden-import openai ^
  --hidden-import httpx ^
  --hidden-import httpcore ^
  --hidden-import anyio ^
  --hidden-import certifi ^
  --hidden-import distro ^
  --hidden-import jiter ^
  --hidden-import sniffio ^
  --hidden-import openpyxl.cell._writer ^
  --collect-submodules openai ^
  --collect-submodules httpx ^
  --collect-submodules httpcore ^
  --collect-submodules anyio ^
  --collect-data certifi ^
  app.py
if errorlevel 1 goto BUILD_FAILED

echo.
echo [4/5] Copying support files...
copy /Y "config.example.ini" "dist\%APP_NAME%\config.example.ini" >nul
copy /Y "README.md" "dist\%APP_NAME%\README.md" >nul

echo.
echo [5/5] Creating zip package...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\zip_dist.ps1" -SourceDir "dist\%APP_NAME%" -DestinationZip "dist\%APP_NAME%.zip" -Retries 6 -DelaySeconds 5
if errorlevel 1 goto ZIP_FAILED

echo.
echo Build finished.
echo EXE: dist\%APP_NAME%\%APP_NAME%.exe
echo ZIP: dist\%APP_NAME%.zip
pause
exit /b 0

:NO_PYTHON
echo python was not found. Please install Python first, then run build_exe.bat again.
pause
exit /b 1

:ZIP_FAILED
echo.
echo EXE build finished, but zip package failed because some files may still be locked.
echo EXE folder is available: dist\%APP_NAME%
echo You can close running exe/antivirus scan and run this command again:
echo powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\zip_dist.ps1" -SourceDir "dist\%APP_NAME%" -DestinationZip "dist\%APP_NAME%.zip"
pause
exit /b 2
