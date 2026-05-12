@echo off
setlocal enabledelayedexpansion
:: ========================================================
:: Lighthouse OCR - Setup chay tu ma nguon (Source Run)
:: Muc dich: Cai dat Python portable + tat ca thu vien can thiet
::           de chay truc tiep bang 'python_env\python.exe main_app_qt.py'
::           Khong can build EXE.
:: ========================================================

set "TITLE=Lighthouse OCR - Thiet lap chay tu nguon"
set "BASE_DIR=%~dp0"
set "PYTHON_DIR=%BASE_DIR%python_env"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "PYTHON_ZIP=%PYTHON_DIR%\python.zip"
set "GET_PIP=%PYTHON_DIR%\get-pip.py"
set "INSTALLER=%TEMP%\vc_redist_lighthouse.x64.exe"
set "HAS_ADMIN=0"
set "LAUNCHER=%BASE_DIR%LighthouseInvoicesOCR.bat"
set "SHORTCUT=%BASE_DIR%LighthouseInvoicesOCR.lnk"

title %TITLE%

echo ========================================================
echo   %TITLE%
echo ========================================================
echo.
echo  Script nay cai dat moi truong day du de chay app
echo  truc tiep tu ma nguon (khong can build EXE).
echo.

:: --- Quyen Admin ---
echo [Checking] Quyen Admin...
net session >nul 2>&1
if %errorLevel% equ 0 (
    set "HAS_ADMIN=1"
    echo [OK] Dang chay voi quyen Admin.
) else (
    echo [INFO] Khong co quyen Admin. Se bo qua cai VC++ neu can.
)

:: ======================================================
:: [1/4] VC++ Redistributable
:: ======================================================
echo.
echo [1/4] Kiem tra Microsoft Visual C++ Redistributable...
if exist "%SystemRoot%\System32\msvcp140.dll" (
    echo [OK] VC++ Redistributable da co san.
) else (
    if "%HAS_ADMIN%"=="1" (
        echo [INFO] Dang tai tu Microsoft...
        powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%INSTALLER%'"
        if errorlevel 1 (
            echo [WARNING] Khong the tai VC++ Redist. Tiep tuc...
        ) else (
            start /wait "" "%INSTALLER%" /install /quiet /norestart
            if exist "%INSTALLER%" del "%INSTALLER%"
            echo [OK] Cai dat VC++ hoan tat.
        )
    ) else (
        echo [WARNING] Thieu VC++ va khong co quyen Admin. Mot so thu vien C++ co the loi.
    )
)

:: ======================================================
:: [2/4] Python 3.10 Portable
:: ======================================================
echo.
echo [2/4] Thiet lap Python 3.10 Portable...
if not exist "%PYTHON_DIR%" mkdir "%PYTHON_DIR%"

if exist "%PYTHON_EXE%" (
    echo [OK] Python embeddable da ton tai: %PYTHON_EXE%
) else (
    echo [INFO] Dang tai Python 3.10.11 embeddable...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip' -OutFile '%PYTHON_ZIP%'"
    if errorlevel 1 (
        echo [ERROR] Tai Python embeddable that bai. Kiem tra Internet.
        goto abort
    )

    echo [INFO] Dang giai nen Python...
    powershell -Command "Expand-Archive -Path '%PYTHON_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force"
    if errorlevel 1 ( echo [ERROR] Giai nen Python that bai. & goto abort )
    if exist "%PYTHON_ZIP%" del "%PYTHON_ZIP%"
    if not exist "%PYTHON_EXE%" ( echo [ERROR] Khong tim thay python.exe sau giai nen. & goto abort )

    echo [INFO] Kich hoat site-packages...
    powershell -Command "(Get-Content '%PYTHON_DIR%\python310._pth') -replace '#import site', 'import site' | Set-Content '%PYTHON_DIR%\python310._pth'"
    if errorlevel 1 ( echo [ERROR] Khong the sua python310._pth. & goto abort )

    echo [INFO] Tai get-pip.py...
    powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GET_PIP%'"
    if errorlevel 1 ( echo [ERROR] Tai get-pip.py that bai. & goto abort )

    echo [INFO] Cai pip...
    "%PYTHON_EXE%" "%GET_PIP%" --no-warn-script-location
    if errorlevel 1 ( echo [ERROR] Cai pip that bai. & goto abort )
    if exist "%GET_PIP%" del "%GET_PIP%"
)

:: ======================================================
:: [3/4] Cai dat tat ca thu vien
:: ======================================================
echo.
echo [3/4] Cai dat thu vien (qua trinh nay tai khoang 500MB-1GB)...

echo [INFO] Cap nhat pip, setuptools, wheel...
"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel --quiet
if errorlevel 1 ( echo [ERROR] Cap nhat pip that bai. & goto abort )

echo [INFO] Cai thu vien UI + xu ly anh + Excel + AI...
"%PYTHON_EXE%" -m pip install ^
    "numpy<2.0.0" ^
    "opencv-python" ^
    "Pillow" ^
    "PyQt5" ^
    "openpyxl" ^
    "google-genai" ^
    "rapidfuzz" ^
    "pytesseract"
if errorlevel 1 (
    echo [ERROR] Cai dat thu vien chinh that bai.
    goto abort
)

echo [INFO] Lam sach goi PaddleOCR/PaddlePaddle cu (neu co)...
"%PYTHON_EXE%" -m pip uninstall -y paddleocr paddlepaddle paddlex >nul 2>&1

echo [INFO] Cai PaddlePaddle 3.3.1 (CPU)...
"%PYTHON_EXE%" -m pip install "paddlepaddle==3.3.1" -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
if errorlevel 1 (
    echo [ERROR] Cai PaddlePaddle that bai.
    goto abort
)

echo [INFO] Cai PaddleOCR 3.5.0...
"%PYTHON_EXE%" -m pip install "paddleocr==3.5.0"
if errorlevel 1 (
    echo [ERROR] Cai PaddleOCR that bai.
    goto abort
)

:: ======================================================
:: [4/4] Warmup mo hinh AI + Tao file launcher
:: ======================================================
echo.
echo [4/4] Tai truoc mo hinh AI (khoang 200MB)...
if exist "%BASE_DIR%ocr_runner.py" (
    "%PYTHON_EXE%" "%BASE_DIR%ocr_runner.py" --warmup
    if errorlevel 1 (
        echo [WARNING] Warmup PaddleOCR that bai. Co the chay lai sau.
    ) else (
        echo [OK] Mo hinh AI da san sang.
    )
) else (
    echo [WARNING] Khong tim thay ocr_runner.py.
)

:: Tao file khoi dong LighthouseInvoicesOCR.bat
echo [INFO] Tao file khoi dong ung dung...
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo start "" "%%~dp0python_env\pythonw.exe" "%%~dp0main_app_qt.py"
) > "%LAUNCHER%"
echo [OK] Da tao: %LAUNCHER%

:: Tao icon cho shortcut (uu tien App_logo.png, fallback icon.ico)
set "ICON_FILE=%BASE_DIR%icon.ico"
if exist "%BASE_DIR%App_logo.png" (
    echo [INFO] Chuyen App_logo.png thanh icon...
    "%PYTHON_EXE%" -c "from PIL import Image; img=Image.open(r'%BASE_DIR%App_logo.png'); img.save(r'%BASE_DIR%launcher_icon.ico')" >nul 2>&1
    if exist "%BASE_DIR%launcher_icon.ico" (
        set "ICON_FILE=%BASE_DIR%launcher_icon.ico"
        echo [OK] Da tao launcher_icon.ico tu App_logo.png.
    ) else (
        echo [WARNING] Khong the chuyen App_logo.png. Dung icon mac dinh.
    )
)

:: Tao shortcut .lnk voi icon
echo [INFO] Tao shortcut LighthouseInvoicesOCR.lnk...
powershell -Command "$s=New-Object -ComObject WScript.Shell; $lnk=$s.CreateShortcut('%SHORTCUT%'); $lnk.TargetPath='%LAUNCHER%'; $lnk.WorkingDirectory='%BASE_DIR%'; $lnk.IconLocation='%ICON_FILE%'; $lnk.Description='Lighthouse Invoices OCR'; $lnk.Save()"
if exist "%SHORTCUT%" (
    echo [OK] Da tao shortcut: %SHORTCUT%
) else (
    echo [WARNING] Khong tao duoc shortcut. Dung truc tiep LighthouseInvoicesOCR.bat.
)

echo.
echo ========================================================
echo   CAI DAT HOAN TAT!
echo.
echo   De chay ung dung:
echo     LighthouseInvoicesOCR.lnk  (shortcut voi icon)
echo   HOAC:
echo     LighthouseInvoicesOCR.bat
echo   HOAC:
echo     python_env\pythonw.exe main_app_qt.py
echo.
echo   Lan dau chay: Vao Settings (banh rang) va nhap
echo   Gemini API Key. Lay key mien phi tai:
echo   https://aistudio.google.com
echo ========================================================
pause
exit /b 0

:abort
echo.
echo ========================================================
echo   THIET LAP THAT BAI
echo ========================================================
echo [INFO] Xem cac thong bao loi o tren de xac dinh buoc bi loi.
echo [INFO] Thu lai hoac kiem tra ket noi Internet.
pause
exit /b 1
