# =============================================================================
# Deploy_Build.ps1 — Lighthouse OCR v7.1 Deployment Script
# =============================================================================
# Mặc định: Build BẢN UPDATE (code app + python_env, không kèm Data structure)
# Để build BẢN FULL: thêm flag -Full
#   powershell -ExecutionPolicy Bypass -File Deploy_Build.ps1 -Full
# =============================================================================

param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"

$ProjectDir  = $PSScriptRoot
$DistDir     = Join-Path $ProjectDir "dist"
$BuildName   = "LighthouseOCR_RELEASE"
$OutputDir   = Join-Path $DistDir $BuildName
$SpecFile    = Join-Path $ProjectDir "LighthouseOCR_v7.0_Folder.spec"
$PythonEnv   = Join-Path $ProjectDir "python_env"
$DataDir     = Join-Path $ProjectDir "Data structure"

$BuildType = if ($Full) { "FULL" } else { "UPDATE" }

Write-Host "======================================================"
Write-Host "  Lighthouse OCR v7.1 Deployment — Bản $BuildType"
Write-Host "======================================================"

# --- Step 1: PyInstaller ---
Write-Host "[1/$( if ($Full) { '4' } else { '3' })] PyInstaller Build..."
pyinstaller $SpecFile --clean -y
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED"
    exit 1
}

# --- Step 2: Copy python_env (luôn cần thiết) ---
Write-Host "[2/$( if ($Full) { '4' } else { '3' })] Copy python_env..."
$DestPythonEnv = Join-Path $OutputDir "python_env"
if (Test-Path $PythonEnv) {
    robocopy $PythonEnv $DestPythonEnv /E /NFL /NDL /NJH /NJS /NC /NS /MT:8
}

# --- Step 3: Config Template ---
Write-Host "[3/$( if ($Full) { '4' } else { '3' })] Config Template..."
$DestConfig = Join-Path $DestPythonEnv "lighthouse_config.json"
$EmptyConfig = @{ hardware_id = ""; api_key = ""; admin_password = ""; models = @{
    light_primary  = "gemini-2.5-flash-preview-04-17"
    light_fallback = "gemini-2.5-flash"
    pro_primary    = "gemini-2.5-pro"
    pro_fallback   = "gemini-2.5-pro"
}} | ConvertTo-Json -Depth 3
Set-Content -Path $DestConfig -Value $EmptyConfig -Encoding UTF8

# --- Step 4 (FULL only): Copy Data structure ---
if ($Full) {
    Write-Host "[4/4] Copy Data structure (FULL build only)..."
    $DestData = Join-Path $OutputDir "Data structure"
    if (Test-Path $DataDir) {
        robocopy $DataDir $DestData /E /NFL /NDL /NJH /NJS /NC /NS /MT:8
    } else {
        Write-Host "  WARNING: 'Data structure' folder not found, skipping."
    }
}

Write-Host "======================================================"
Write-Host "  DONE — Bản $BuildType tại: $OutputDir"
Write-Host "======================================================"
