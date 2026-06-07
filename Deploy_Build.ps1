# =============================================================================
# Deploy_Build.ps1 - Lighthouse OCR Deployment Script
# =============================================================================
# Mac dinh: Build BAN UPDATE (code app + env runtime + bootstrap scripts)
# De build BAN FULL: them flag -Full (bo sung de quyet dinh lai Data structure)
#   powershell -ExecutionPolicy Bypass -File Deploy_Build.ps1 -Full
# =============================================================================

param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"

$ProjectDir      = $PSScriptRoot
$DistDir         = Join-Path $ProjectDir "dist"
$BuildOutputDir  = Join-Path $DistDir "LighthouseOCR"   # final output in project
$SpecFile        = Join-Path $ProjectDir "LighthouseOCR.spec"
$StructureRunner = Join-Path $ProjectDir "ocr_structure_runner.py"
$PrimaryEnvDir   = Join-Path $ProjectDir "env"
$LegacyEnvDir    = Join-Path $ProjectDir "python_env"
$DataDir         = Join-Path $ProjectDir "Data structure"
$ClientSetupBat  = Join-Path $ProjectDir "Setup_Moi_Truong.bat"
$MainAppFile     = Join-Path $ProjectDir "main_app_qt.py"
$TempRoot        = Join-Path $ProjectDir (".build_tmp\\lhocr_build_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
$TempDistDir     = Join-Path $TempRoot "dist"
$TempBuildDir    = Join-Path $TempRoot "build"
$TempOutputDir   = Join-Path $TempDistDir "LighthouseOCR"

$BuildType = if ($Full) { "FULL" } else { "UPDATE" }
$TotalSteps = if ($Full) { 5 } else { 4 }
$AppVersion = "unknown"

if (Test-Path $MainAppFile) {
    $m = Select-String -Path $MainAppFile -Pattern '^\s*APP_VERSION\s*=\s*"([^"]+)"'
    if ($m -and $m.Matches.Count -gt 0) {
        $AppVersion = $m.Matches[0].Groups[1].Value
    }
}

Write-Host "======================================================"
Write-Host "  Lighthouse OCR $AppVersion Deployment - Ban $BuildType"
Write-Host "======================================================"

if (-not (Test-Path $SpecFile)) {
    throw "Khong tim thay spec file: $SpecFile"
}

# --- Step 1: PyInstaller ---
Write-Host "[1/$TotalSteps] PyInstaller Build..."
New-Item -ItemType Directory -Force -Path $TempRoot, $TempDistDir, $TempBuildDir | Out-Null

$EnvPython = Join-Path $PrimaryEnvDir "python.exe"
if (-not (Test-Path $EnvPython)) {
    $EnvPython = Join-Path $PrimaryEnvDir "Scripts\python.exe"
}
if (Test-Path $EnvPython) {
    if (Test-Path $StructureRunner) {
        Write-Host "  Preflight: PP-StructureV3 runtime check..."
        & $EnvPython $StructureRunner --check
        if ($LASTEXITCODE -ne 0) {
            throw "PP-StructureV3 runtime check failed. Run Setup_Moi_Truong.bat or Setup_Nguon.bat before building."
        }
    } else {
        throw "Khong tim thay ocr_structure_runner.py de kiem tra PP-StructureV3."
    }
    & $EnvPython -m PyInstaller $SpecFile --clean -y --workpath $TempBuildDir --distpath $TempDistDir
} else {
    Write-Host "  WARNING: Khong tim thay env python de kiem tra PP-StructureV3 truoc build."
    pyinstaller $SpecFile --clean -y --workpath $TempBuildDir --distpath $TempDistDir
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED"
    exit 1
}

# --- Step 2: Copy env (luon can thiet) ---
Write-Host "[2/$TotalSteps] Copy env..."
$SourceEnv = $null
if (Test-Path $PrimaryEnvDir) {
    $SourceEnv = $PrimaryEnvDir
} elseif (Test-Path $LegacyEnvDir) {
    # Backward compatibility for old hierarchy
    $SourceEnv = $LegacyEnvDir
}

if (-not (Test-Path $TempOutputDir)) {
    throw "Khong tim thay thu muc output sau build: $TempOutputDir"
}

# sync temp dist -> project dist
if (Test-Path $BuildOutputDir) {
    Remove-Item -LiteralPath $BuildOutputDir -Recurse -Force
}
robocopy $TempOutputDir $BuildOutputDir /E /NFL /NDL /NJH /NJS /NC /NS /MT:8
if ($LASTEXITCODE -gt 7) {
    throw "Robocopy output that bai (exit code: $LASTEXITCODE)"
}

$DestEnv = Join-Path $BuildOutputDir "env"
if ($SourceEnv) {
    robocopy $SourceEnv $DestEnv /E /NFL /NDL /NJH /NJS /NC /NS /MT:8
    if ($LASTEXITCODE -gt 7) {
        throw "Robocopy env that bai (exit code: $LASTEXITCODE)"
    }
} else {
    Write-Host "  WARNING: Khong tim thay env hoac python_env de copy."
}

# --- Step 3: Client bootstrap scripts ---
Write-Host "[3/$TotalSteps] Client bootstrap scripts..."
if (Test-Path $ClientSetupBat) {
    Copy-Item -LiteralPath $ClientSetupBat -Destination $BuildOutputDir -Force
} else {
    Write-Host "  WARNING: Khong tim thay Setup_Moi_Truong.bat. Client se khong co script tu-sua dependencies."
}

$ClientLauncherPath = Join-Path $BuildOutputDir "LighthouseOCR_Start.bat"
$LauncherContent = @"
@echo off
setlocal
set "BASE_DIR=%~dp0"
set "APP_EXE=%BASE_DIR%LighthouseOCR.exe"
set "PYTHON_EXE=%BASE_DIR%env\python.exe"
set "SETUP_BAT=%BASE_DIR%Setup_Moi_Truong.bat"

if not exist "%APP_EXE%" (
    echo [ERROR] Khong tim thay LighthouseOCR.exe trong thu muc hien tai.
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" goto needs_setup
"%PYTHON_EXE%" -c "print('ok')" >nul 2>&1
if errorlevel 1 goto needs_setup

start "" "%APP_EXE%"
exit /b 0

:needs_setup
echo [INFO] Moi truong OCR hoac dependencies chua san sang.
if not exist "%SETUP_BAT%" (
    echo [ERROR] Khong tim thay Setup_Moi_Truong.bat de sua moi truong.
    echo [INFO] Hay copy file setup vao cung thu muc voi LighthouseOCR.exe.
    pause
    exit /b 1
)
choice /C YN /N /M "Chay Setup_Moi_Truong.bat ngay bay gio? [Y/N]"
if errorlevel 2 goto cancelled
call "%SETUP_BAT%"
if errorlevel 1 goto setup_failed

if not exist "%PYTHON_EXE%" goto setup_failed
"%PYTHON_EXE%" -c "print('ok')" >nul 2>&1
if errorlevel 1 goto setup_failed

start "" "%APP_EXE%"
exit /b 0

:setup_failed
echo [ERROR] Setup_Moi_Truong.bat chay chua thanh cong.
echo [INFO] Kiem tra log trong cua so setup va thu lai voi quyen Admin.
pause
exit /b 1

:cancelled
echo [INFO] Da huy setup. Ung dung khong the chay khi thieu dependencies.
pause
exit /b 1
"@
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ClientLauncherPath, $LauncherContent, $Utf8NoBom)

# --- Step 4: Config Template ---
Write-Host "[4/$TotalSteps] Config Template..."
$DestConfig = Join-Path $DestEnv "lighthouse_config.json"
$EmptyConfig = @{ hardware_id = ""; api_key = ""; admin_password = ""; ocr_mode = "stable"; ocr_pipeline_mode = "structure_default"; models = @{
    light_primary  = "gemini-3.1-flash-lite"
    light_fallback = "gemini-2.5-flash"
    pro_primary    = "gemini-3.5-flash"
    pro_fallback   = "gemini-3.1-pro-preview"
}} | ConvertTo-Json -Depth 3
if (Test-Path $DestEnv) {
    [System.IO.File]::WriteAllText($DestConfig, $EmptyConfig, $Utf8NoBom)
} else {
    Write-Host "  WARNING: Bo qua tao lighthouse_config.json vi thu muc env chua ton tai."
}

# --- Step 5 (FULL only): Copy Data structure ---
if ($Full) {
    Write-Host "[5/5] Copy Data structure - FULL build only..."
    $DestData = Join-Path $BuildOutputDir "Data structure"
    if (Test-Path $DataDir) {
        robocopy $DataDir $DestData /E /NFL /NDL /NJH /NJS /NC /NS /MT:8
        if ($LASTEXITCODE -gt 7) {
            throw "Robocopy Data structure that bai (exit code: $LASTEXITCODE)"
        }
    } else {
        Write-Host "  WARNING: 'Data structure' folder not found, skipping."
    }
}

Write-Host "======================================================"
Write-Host "  DONE - Ban $BuildType tai: $BuildOutputDir"
Write-Host "======================================================"
