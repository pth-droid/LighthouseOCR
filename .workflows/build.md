# Build Lighthouse OCR (EXE Only)

Quy trình này chỉ biên dịch lại file `LighthouseOCR.exe` bằng PyInstaller, bỏ qua bước copy thư viện `python_env` nặng nề. Phù hợp khi bạn chỉ sửa đổi code giao diện hoặc logic Python mà không thay đổi thư viện AI.

// turbo-all

1. **Clear previous build artifacts**
   ```powershell
   if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
   ```

2. **Run PyInstaller**
   ```powershell
   pyinstaller LighthouseOCR_v7.0_Folder.spec --clean -y
   ```

3. **Verify Build Output**
   ```powershell
   ls "dist\LighthouseOCR_RELEASE\LighthouseOCR.exe"
   ```
