@echo off
cd /d "%~dp0"
set UV_CACHE_DIR=%CD%\.uv_cache

python --version >nul 2>nul
if errorlevel 1 goto TRY_UV

python app.py --cli %*
exit /b %errorlevel%

:TRY_UV
where uv >nul 2>nul
if errorlevel 1 goto NO_RUNTIME

echo %* | findstr /C:"--test-api" >nul
if not errorlevel 1 (
  echo %* | findstr /C:"--mock" >nul
  if not errorlevel 1 (
    uv run python app.py --cli %*
    exit /b %errorlevel%
  )
  uv run --with openai python app.py --cli %*
  exit /b %errorlevel%
)

uv run --with openai --with Pillow --with openpyxl python app.py --cli %*
exit /b %errorlevel%

:NO_RUNTIME
echo Python or uv was not found. Please install Python 3.11+ or uv.
pause
exit /b 1
