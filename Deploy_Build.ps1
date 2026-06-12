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

function ConvertTo-QuotedProcessArgument {
    param([string]$Argument)

    if ($null -eq $Argument) {
        return '""'
    }
    return '"' + ($Argument -replace '"', '\"') + '"'
}

function Invoke-NativeToLog {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$LogPath
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = (($Arguments | ForEach-Object { ConvertTo-QuotedProcessArgument $_ }) -join " ")
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()

    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    $proc.WaitForExit()

    $Utf8NoBomForLog = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($LogPath, ($stdoutTask.Result + $stderrTask.Result), $Utf8NoBomForLog)
    return $proc.ExitCode
}

function Invoke-PyInstallerBuildWithRetry {
    param(
        [string]$PythonExe,
        [string]$SpecPath,
        [string]$BuildRoot,
        [string]$DistPath,
        [bool]$UsePythonModule = $true,
        [int]$MaxAttempts = 3
    )

    $script:PyInstallerExitCode = 1
    for ($PyInstallerAttempt = 1; $PyInstallerAttempt -le $MaxAttempts; $PyInstallerAttempt++) {
        $AttemptBuildDir = Join-Path $BuildRoot ("pyinstaller_attempt_" + $PyInstallerAttempt)
        if (Test-Path $AttemptBuildDir) {
            Remove-Item -LiteralPath $AttemptBuildDir -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $AttemptBuildDir | Out-Null

        if ($UsePythonModule) {
            & $PythonExe -m PyInstaller $SpecPath --clean -y --workpath $AttemptBuildDir --distpath $DistPath
        } else {
            pyinstaller $SpecPath --clean -y --workpath $AttemptBuildDir --distpath $DistPath
        }
        $script:PyInstallerExitCode = $LASTEXITCODE
        if ($script:PyInstallerExitCode -eq 0) {
            return
        }

        Write-Host "  PyInstaller failed on attempt $PyInstallerAttempt/$MaxAttempts (exit code: $script:PyInstallerExitCode)."
        if ($PyInstallerAttempt -lt $MaxAttempts) {
            Start-Sleep -Seconds (5 * $PyInstallerAttempt)
        }
    }
}

function Test-WindowsResourceUpdate {
    param(
        [string]$PythonExe,
        [string]$ProbeRoot
    )

    $ProbeScript = Join-Path $ProbeRoot "pyinstaller_resource_probe.py"
    $ProbeTarget = Join-Path $ProbeRoot "pyinstaller_resource_probe.exe"
    $ProbeLog = Join-Path $ProbeRoot "pyinstaller_resource_probe.log"
    # NOTE: PyInstaller 6.x removed PyInstaller.compat.PLATFORM. The previous
    # probe imported it and always raised ImportError, so this check always
    # "failed" and the build always set LHOCR_SKIP_WIN_RESOURCE_UPDATE=1 -> the
    # app manifest was stripped from the exe -> missing Common-Controls v6
    # dependency -> "ordinal 380 could not be located in COMCTL32.dll" crash on
    # client machines. Locate the bootloader via glob (version-agnostic) and
    # verify BOTH resource removal AND manifest embedding actually work.
    $ProbeCode = @"
import glob
import os
import shutil
import sys
from PyInstaller import HOMEPATH
from PyInstaller.utils.win32 import winresource, winmanifest

cands = glob.glob(os.path.join(HOMEPATH, "PyInstaller", "bootloader", "*", "runw.exe"))
if not cands:
    cands = glob.glob(os.path.join(HOMEPATH, "PyInstaller", "bootloader", "*", "run.exe"))
if not cands:
    raise SystemExit("bootloader exe not found under PyInstaller/bootloader")
src = cands[0]
target = sys.argv[1]
if os.path.exists(target):
    os.unlink(target)
shutil.copyfile(src, target)
winresource.remove_all_resources(target)
xml = winmanifest._DEFAULT_MANIFEST_XML
if not isinstance(xml, bytes):
    xml = xml.encode("utf-8")
winmanifest.write_manifest_to_executable(target, xml)
print("resource update ok")
"@

    $Utf8NoBomForProbe = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($ProbeScript, $ProbeCode, $Utf8NoBomForProbe)
    $ProbeExitCode = Invoke-NativeToLog -FilePath $PythonExe -Arguments @($ProbeScript, $ProbeTarget) -LogPath $ProbeLog
    return ($ProbeExitCode -eq 0)
}

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
$TotalSteps = if ($Full) { 6 } else { 5 }
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
        $PreflightLog = Join-Path $TempRoot "pp_structure_preflight.log"
        $PreflightExitCode = Invoke-NativeToLog -FilePath $EnvPython -Arguments @($StructureRunner, "--check") -LogPath $PreflightLog
        if ($PreflightExitCode -ne 0) {
            Write-Host "  PP-StructureV3 runtime check failed. Log:"
            if (Test-Path $PreflightLog) {
                Get-Content -LiteralPath $PreflightLog
            }
            throw "PP-StructureV3 runtime check failed. Run Setup_Moi_Truong.bat or Setup_Nguon.bat before building."
        }
        Write-Host "  PP-StructureV3 runtime check OK."
    } else {
        throw "Khong tim thay ocr_structure_runner.py de kiem tra PP-StructureV3."
    }
    Remove-Item Env:\LHOCR_SKIP_WIN_RESOURCE_UPDATE -ErrorAction SilentlyContinue
    if (-not (Test-WindowsResourceUpdate -PythonExe $EnvPython -ProbeRoot $TempRoot)) {
        $env:LHOCR_SKIP_WIN_RESOURCE_UPDATE = "1"
        Write-Host "  WARNING: Windows blocked EXE resource updates; building without embedded EXE icon/manifest resources."
    }
    Invoke-PyInstallerBuildWithRetry -PythonExe $EnvPython -SpecPath $SpecFile -BuildRoot $TempBuildDir -DistPath $TempDistDir -UsePythonModule $true
} else {
    Write-Host "  WARNING: Khong tim thay env python de kiem tra PP-StructureV3 truoc build."
    Invoke-PyInstallerBuildWithRetry -PythonExe "" -SpecPath $SpecFile -BuildRoot $TempBuildDir -DistPath $TempDistDir -UsePythonModule $false
}
if ($script:PyInstallerExitCode -ne 0) {
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

# sync temp dist -> project dist. The exe is removed first; if it is locked we
# spill into a fresh timestamped folder so the new build is never mixed with an
# in-use one.
$ExistingExePath = Join-Path $BuildOutputDir "LighthouseOCR.exe"
if (Test-Path $ExistingExePath) {
    try {
        Remove-Item -LiteralPath $ExistingExePath -Force
    } catch {
        $BuildOutputDir = Join-Path $DistDir ("LighthouseOCR_locked_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
        Write-Host "  WARNING: Existing app output is locked; writing this build to: $BuildOutputDir"
    }
}
New-Item -ItemType Directory -Force -Path $BuildOutputDir | Out-Null

# Delete the stale _internal before copying. PyInstaller folder builds must be
# replaced wholesale: overlaying a new build onto an old _internal leaves stale
# DLLs whose export tables no longer match, which triggers runtime
# "ordinal could not be located in the dynamic link library" crashes.
$ExistingInternal = Join-Path $BuildOutputDir "_internal"
if (Test-Path $ExistingInternal) {
    Write-Host "  Removing stale _internal to avoid mixed-DLL bundle..."
    try {
        Remove-Item -LiteralPath $ExistingInternal -Recurse -Force
    } catch {
        $BuildOutputDir = Join-Path $DistDir ("LighthouseOCR_locked_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
        Write-Host "  WARNING: _internal is locked; writing this build to: $BuildOutputDir"
        New-Item -ItemType Directory -Force -Path $BuildOutputDir | Out-Null
    }
}
robocopy $TempOutputDir $BuildOutputDir /E /NFL /NDL /NJH /NJS /NC /NS /NP /MT:8
if ($LASTEXITCODE -gt 7) {
    throw "Robocopy output that bai (exit code: $LASTEXITCODE)"
}

# --- Manifest safety net ---
# The exe MUST embed an application manifest declaring the Common-Controls v6
# dependency, otherwise Windows binds it to the legacy comctl32 v5 and the
# bootloader's "COMCTL32.dll ordinal 380" import fails at launch on client
# machines. Verify the final exe; repair in-place if the manifest is missing.
$FinalExe = Join-Path $BuildOutputDir "LighthouseOCR.exe"
if ((Test-Path $FinalExe) -and (Test-Path $EnvPython)) {
    Write-Host "  Verifying embedded application manifest (Common-Controls v6)..."
    $ManifestFix = Join-Path $TempRoot "ensure_manifest.py"
    $ManifestCode = @"
import sys
from PyInstaller.utils.win32 import winmanifest
exe = sys.argv[1]
def _has_cc():
    try:
        m = winmanifest.read_manifest_from_executable(exe)
        m = m if isinstance(m, bytes) else (m or "").encode("utf-8")
        return b"Common-Controls" in m
    except Exception:
        return False
if _has_cc():
    print("MANIFEST_OK")
else:
    xml = winmanifest._DEFAULT_MANIFEST_XML
    if not isinstance(xml, bytes):
        xml = xml.encode("utf-8")
    winmanifest.write_manifest_to_executable(exe, xml)
    print("MANIFEST_REPAIRED" if _has_cc() else "MANIFEST_FAILED")
"@
    $Utf8NoBomManifest = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($ManifestFix, $ManifestCode, $Utf8NoBomManifest)
    $ManifestLog = Join-Path $TempRoot "ensure_manifest.log"
    $null = Invoke-NativeToLog -FilePath $EnvPython -Arguments @($ManifestFix, $FinalExe) -LogPath $ManifestLog
    $ManifestResult = (Get-Content -LiteralPath $ManifestLog -Raw -ErrorAction SilentlyContinue)
    if ($ManifestResult -match "MANIFEST_OK") {
        Write-Host "  Manifest OK (embedded)."
    } elseif ($ManifestResult -match "MANIFEST_REPAIRED") {
        Write-Host "  Manifest was missing; repaired in-place."
    } else {
        # Last-resort fallback: external manifest. Windows honors
        # <exe>.manifest when the exe has no embedded manifest.
        Write-Host "  WARNING: Could not embed manifest; writing external LighthouseOCR.exe.manifest fallback."
        $ExternalManifest = $FinalExe + ".manifest"
        $ExtManifestXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <dependency>
    <dependentAssembly>
      <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/>
    </dependentAssembly>
  </dependency>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security><requestedPrivileges><requestedExecutionLevel level="asInvoker" uiAccess="false"/></requestedPrivileges></security>
  </trustInfo>
</assembly>
"@
        [System.IO.File]::WriteAllText($ExternalManifest, $ExtManifestXml, $Utf8NoBomManifest)
    }
}

$DestEnv = Join-Path $BuildOutputDir "env"
if ($SourceEnv) {
    robocopy $SourceEnv $DestEnv /E /NFL /NDL /NJH /NJS /NC /NS /NP /MT:8 /XD __pycache__ /XF *.pyc *.pyo
    if ($LASTEXITCODE -gt 7) {
        throw "Robocopy env that bai (exit code: $LASTEXITCODE)"
    }
    if (Test-Path $DestEnv) {
        Get-ChildItem -LiteralPath $DestEnv -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
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

# --- Step 5: Data structure (single source of truth at the app root) ---
# "Data structure" is user-editable master data (templates, master lists,
# Tu_dien_alias.csv). It is NOT bundled into _internal (see LighthouseOCR.spec).
#   FULL  : ship a fresh baseline copy at the app root (new install).
#   UPDATE: do NOT ship it, and strip any leftover copy from the build output,
#           so extracting the update zip never overwrites the client's edited
#           master data / alias dictionary.
$DestData = Join-Path $BuildOutputDir "Data structure"
if ($Full) {
    Write-Host "[5/$TotalSteps] Copy Data structure (FULL - fresh install baseline)..."
    if (Test-Path $DataDir) {
        robocopy $DataDir $DestData /E /NFL /NDL /NJH /NJS /NC /NS /NP /MT:8
        if ($LASTEXITCODE -gt 7) {
            throw "Robocopy Data structure that bai (exit code: $LASTEXITCODE)"
        }
    } else {
        Write-Host "  WARNING: 'Data structure' folder not found, skipping."
    }
} else {
    Write-Host "[5/$TotalSteps] UPDATE build - giu nguyen Data structure cua client..."
    if (Test-Path $DestData) {
        Write-Host "  Removing leftover Data structure from build output (update zip must not overwrite client data)."
        Remove-Item -LiteralPath $DestData -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# --- Final step: package the built folder into a single zip for delivery ---
Write-Host "[$TotalSteps/$TotalSteps] Dong goi ZIP de gui di..."
$FolderName = Split-Path $BuildOutputDir -Leaf
$ZipName    = "{0}_{1}_{2}.zip" -f $FolderName, $AppVersion, (Get-Date -Format "yyyyMMdd_HHmmss")
$ZipPath    = Join-Path $DistDir $ZipName
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
}
try {
    # Use the .NET zip API directly: Compress-Archive is slow/limited on large
    # trees (the env/ + _internal payload is big). The zip lands in dist\, NOT
    # inside the build folder, so it never tries to compress itself.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $BuildOutputDir,
        $ZipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $true   # includeBaseDirectory: client gets a single top-level folder when extracted
    )
    $ZipSizeMB = [math]::Round((Get-Item -LiteralPath $ZipPath).Length / 1MB, 1)
    Write-Host "  ZIP da tao: $ZipPath ($ZipSizeMB MB)"
} catch {
    Write-Host "  WARNING: Khong the tao ZIP: $($_.Exception.Message)"
    Write-Host "  Ban van co the gui truc tiep thu muc: $BuildOutputDir"
    $ZipPath = $null
}

Write-Host "======================================================"
Write-Host "  DONE - Ban $BuildType tai: $BuildOutputDir"
if ($ZipPath) {
    Write-Host "  ZIP gui di: $ZipPath"
}
Write-Host "======================================================"
