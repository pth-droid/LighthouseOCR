# Full Deployment Build

Quy trình này đóng gói toàn bộ ứng dụng, bao gồm cả file thực thi `LighthouseOCR.exe` và môi trường Python độc lập `python_env` chứa PaddleOCR. 

// turbo-all

1. **Clear previous distribution**
   ```powershell
   if (Test-Path "dist\LighthouseOCR_RELEASE") { Remove-Item "dist\LighthouseOCR_RELEASE" -Recurse -Force }
   ```

2. **Run Deploy Script**
   ```powershell
   .\Deploy_Build.ps1
   ```

3. **Verify final release folder**
   ```powershell
   ls "dist\LighthouseOCR_RELEASE\python_env\python.exe"
   ls "dist\LighthouseOCR_RELEASE\LighthouseOCR.exe"
   ```
