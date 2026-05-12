@echo off
chcp 65001 >nul
color 0B
title Khởi động PPOCRLabel - Môi trường GPU

echo ===================================================
echo     KHOI DONG CONG CU GAN NHAN PPOCRLabel (GPU)
echo ===================================================
echo.

:: Sử dụng môi trường python_env (để tránh lỗi permission và index trên Windows)
set PYTHON_EXE=.\python_env\python.exe

echo [1/2] Kiem tra moi truong Python...
%PYTHON_EXE% --version
if %errorlevel% neq 0 (
    echo [Loi] Khong tim thay Python.
    pause
    exit /b
)

:: Kiem tra xem PPOCRLabel da duoc cai dat chua
%PYTHON_EXE% -c "import PPOCRLabel" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [!] PPOCRLabel chua duoc cai dat hoac can cap nhat. Dang tien hanh cai dat...
    echo Luu y: Buoc nay chi thuc hien 1 lan duy nhat.
    %PYTHON_EXE% -m pip install "PPOCRLabel<3" "paddleocr<2.8" "paddlepaddle-gpu==2.6.2" -q --no-warn-script-location
    
    :: Thu import lai sau khi cai dat
    %PYTHON_EXE% -c "import PPOCRLabel" 2>nul
    if %errorlevel% neq 0 (
        echo [Loi] Khong the nap PPOCRLabel. Vui long kiem tra ket noi mang hoac bao loi lai.
        pause
        exit /b
    )
)

echo.
echo [2/2] Dang khoi dong giao dien PPOCRLabel...
echo.
echo Luu y: Giao dien PPOCRLabel se duoc mo len. 
echo - Vao menu File -^> Open Dir de chon thu muc chua anh can label.
echo - Xem huong dan su dung phim tat trong giao dien.
echo.

%PYTHON_EXE% -c "from PPOCRLabel import PPOCRLabel; PPOCRLabel.main()" --lang vi

pause
