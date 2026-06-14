@echo off
cd /d "%~dp0"
set UV_CACHE_DIR=%CD%\.uv_cache
set UV_LOCK_TIMEOUT=1800
if "%UV_DEFAULT_INDEX%"=="" set UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

python --version >nul 2>nul
if errorlevel 1 goto TRY_UV

python app.py
exit /b %errorlevel%

:TRY_UV
where uv >nul 2>nul
if errorlevel 1 goto NO_RUNTIME

uv run --with openai --with PySide6-Essentials --with Pillow --with openpyxl python app.py
exit /b %errorlevel%

:NO_RUNTIME
echo Python or uv was not found. Please install Python 3.11+ or uv.
pause
exit /b 1
