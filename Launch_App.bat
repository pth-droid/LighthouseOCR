@echo off
:: Lighthouse OCR - App Launcher
:: Uses bundled Python 3.10 to guarantee correct dependencies (PyQt5, PaddleOCR, etc.)

set "BASE_DIR=%~dp0"
set "PYTHON_EXE=%BASE_DIR%python_env\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Khong tim thay Python tai: %PYTHON_EXE%
    echo [INFO] Hay chay Setup_Moi_Truong.bat truoc.
    pause
    exit /b 1
)

"%PYTHON_EXE%" "%BASE_DIR%main_app_qt.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Ung dung thoat voi loi. Ma loi: %errorlevel%
    pause
)
