@echo off
setlocal enabledelayedexpansion
:: Lighthouse OCR - System Environment Setup Script
:: Purpose: Install optional VC++ runtime, portable Python 3.10, dependencies, and warmup OCR models.

set "TITLE=Lighthouse OCR - Thiet lap moi truong he thong"
set "BASE_DIR=%~dp0"
set "PYTHON_DIR=%BASE_DIR%env"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "PYTHON_ZIP=%PYTHON_DIR%\python.zip"
set "GET_PIP=%PYTHON_DIR%\get-pip.py"
set "INSTALLER=%TEMP%\vc_redist_lighthouse.x64.exe"
set "HAS_ADMIN=0"
set "OCR_STACK=ppocrv5"

if /I "%~1"=="legacy" set "OCR_STACK=legacy"

title %TITLE%

echo ========================================================
echo   %TITLE%
echo ========================================================
echo.
echo [INFO] OCR stack target: %OCR_STACK%

echo [Checking] Quyen Admin...
net session >nul 2>&1
if %errorLevel% equ 0 (
    set "HAS_ADMIN=1"
    echo [OK] Dang chay voi quyen Admin.
) else (
    echo [INFO] Khong co quyen Admin. Se bo qua buoc cai VC++ neu can.
)

echo.
echo [1/3] Kiem tra Microsoft Visual C++ Redistributable...
if exist "%SystemRoot%\System32\msvcp140.dll" (
    echo [INFO] Microsoft Visual C++ Redistributable da co san.
) else (
    if "%HAS_ADMIN%"=="1" (
        echo [INFO] Dang tai bo cai tu Microsoft...
        powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%INSTALLER%'"
        if errorlevel 1 (
            echo [ERROR] Khong the tai bo cai Microsoft Visual C++ Redistributable.
            goto abort
        )
        if not exist "%INSTALLER%" (
            echo [ERROR] Khong tim thay file bo cai Microsoft Visual C++ sau khi tai.
            goto abort
        )

        echo [INFO] Dang cai dat Microsoft Visual C++ Redistributable...
        start /wait "" "%INSTALLER%" /install /quiet /norestart
        if errorlevel 1 (
            echo [WARNING] Cai dat VC++ Redist tra ve ma loi %errorLevel%. Van tiep tuc cai Python portable.
        ) else (
            echo [OK] Cai dat VC++ Redist hoan tat.
        )
        if exist "%INSTALLER%" del "%INSTALLER%"
    ) else (
        echo [WARNING] Thieu VC++ Redistributable va script khong co quyen Admin.
        echo [WARNING] Phan cai Python portable van tiep tuc, nhung may co the can cai VC++ thu cong de chay mot so thu vien native.
    )
)

echo.
echo [2/3] CAI DAT MOI TRUONG PYTHON (OCR)...
if not exist "%PYTHON_DIR%" mkdir "%PYTHON_DIR%"

if exist "%PYTHON_EXE%" (
    echo [INFO] Python embeddable da ton tai: %PYTHON_EXE%
) else (
    echo [INFO] Dang tai Python 3.10.11 embeddable...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip' -OutFile '%PYTHON_ZIP%'"
    if errorlevel 1 (
        echo [ERROR] Tai Python embeddable that bai. Vui long kiem tra Internet.
        goto abort
    )
    if not exist "%PYTHON_ZIP%" (
        echo [ERROR] Khong tim thay file python.zip sau khi tai.
        goto abort
    )

    echo [INFO] Dang giai nen Python...
    powershell -Command "Expand-Archive -Path '%PYTHON_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force"
    if errorlevel 1 (
        echo [ERROR] Giai nen Python that bai.
        goto abort
    )
    if exist "%PYTHON_ZIP%" del "%PYTHON_ZIP%"

    if not exist "%PYTHON_EXE%" (
        echo [ERROR] Khong tim thay python.exe sau khi giai nen.
        goto abort
    )

    echo [INFO] Cau hinh embeddable Python de ho tro site-packages...
    powershell -Command "(Get-Content '%PYTHON_DIR%\python310._pth') -replace '#import site', 'import site' | Set-Content '%PYTHON_DIR%\python310._pth'"
    if errorlevel 1 (
        echo [ERROR] Khong the cau hinh file python310._pth.
        goto abort
    )

    echo [INFO] Dang tai get-pip.py...
    powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GET_PIP%'"
    if errorlevel 1 (
        echo [ERROR] Tai get-pip.py that bai.
        goto abort
    )
    if not exist "%GET_PIP%" (
        echo [ERROR] Khong tim thay get-pip.py sau khi tai.
        goto abort
    )

    echo [INFO] Dang cai dat pip...
    "%PYTHON_EXE%" "%GET_PIP%" --no-warn-script-location
    if errorlevel 1 (
        echo [ERROR] Cai dat pip that bai.
        goto abort
    )
    if exist "%GET_PIP%" del "%GET_PIP%"
)

echo.
echo [INFO] Dang cai dat thu vien AI (qua trinh nay se tai kha nhieu du lieu)...
"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [ERROR] Cai dat pip/setuptools/wheel that bai.
    goto abort
)

echo [INFO] Dang lam sach cac goi PaddleOCR/PaddlePaddle cu...
"%PYTHON_EXE%" -m pip uninstall -y paddleocr paddlepaddle paddlex >nul 2>&1

if /I "%OCR_STACK%"=="legacy" (
    echo [INFO] Cai stack LEGACY: PaddleOCR 2.7.3 + PP-OCRv4 compatibility.
    "%PYTHON_EXE%" -m pip install "numpy<2.0.0" "opencv-python" "paddlepaddle==2.6.2" "paddleocr==2.7.3"
    if errorlevel 1 (
        echo [ERROR] Cai dat stack LEGACY that bai.
        goto abort
    )
) else (
    echo [INFO] Cai stack PP-OCRv5: PaddlePaddle 3.3.1 + PaddleOCR 3.6.0.
    "%PYTHON_EXE%" -m pip install "numpy<2.0.0" "opencv-python"
    if errorlevel 1 (
        echo [ERROR] Cai dat numpy/opencv that bai.
        goto abort
    )
    "%PYTHON_EXE%" -m pip install "paddlepaddle==3.3.1" -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
    if errorlevel 1 (
        echo [ERROR] Cai dat PaddlePaddle 3.3.1 that bai.
        goto abort
    )
    "%PYTHON_EXE%" -m pip install "paddleocr==3.6.0"
    if errorlevel 1 (
        echo [ERROR] Cai dat PaddleOCR 3.6.0 that bai.
        goto abort
    )
)

echo [INFO] Cai dat rapidfuzz (ho tro tim kiem ten hang nhanh)...
"%PYTHON_EXE%" -m pip install "rapidfuzz"
if errorlevel 1 (
    echo [ERROR] Cai dat rapidfuzz that bai.
    goto abort
)

echo [INFO] Cai dat pytesseract (ho tro phat hien goc xoay anh)...
"%PYTHON_EXE%" -m pip install "pytesseract"
if errorlevel 1 (
    echo [WARNING] Cai dat pytesseract that bai. Tinh nang phat hien goc xoay co the khong hoat dong.
    echo [WARNING] Neu muon su dung tinh nang nay, cai Tesseract-OCR tu: https://github.com/UB-Mannheim/tesseract/wiki
)

echo.
echo [3/3] TAI TRUOC MO HINH AI (WARMUP)...
if exist "%BASE_DIR%ocr_runner.py" (
    "%PYTHON_EXE%" "%BASE_DIR%ocr_runner.py" --warmup
    if errorlevel 1 (
        echo [ERROR] Warmup PaddleOCR that bai.
        goto abort
    )
) else (
    echo [WARNING] Khong tim thay ocr_runner.py de warmup model.
)

echo.
echo ========================================================
echo   HE THONG DA SAN SANG!
echo   Ban co the chay 'LighthouseOCR.exe' ngay bay gio.
echo ========================================================
pause
exit /b 0

:abort
echo.
echo ========================================================
echo   THIET LAP CHUA HOAN TAT
echo ========================================================
echo [INFO] Neu khong mo bang "Run as Administrator", ban van co the cai Python portable.
echo [INFO] Hay doc cac dong loi o tren de xac dinh buoc dang bi hong.
pause
exit /b 1
