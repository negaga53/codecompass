# ---------------------------------------------------------------
# CodeCompass - Interactive Setup Script (Windows PowerShell)
# ---------------------------------------------------------------
#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# -- Colors & Helpers -------------------------------------------
function Write-Ok   { param([string]$Msg) Write-Host "  [OK] $Msg" -ForegroundColor Green }
function Write-Fail { param([string]$Msg) Write-Host "  [X]  $Msg" -ForegroundColor Red }
function Write-Info { param([string]$Msg) Write-Host "  ->   $Msg" -ForegroundColor Blue }
function Write-Warn { param([string]$Msg) Write-Host "  !    $Msg" -ForegroundColor Yellow }

function Write-Header {
    param([string]$Title)
    Write-Host ''
    Write-Host '--------------------------------------------------------------' -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor White
    Write-Host '--------------------------------------------------------------' -ForegroundColor Cyan
}

# -- Resolve script directory -----------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Header 'CodeCompass Setup'
Write-Host ''
Write-Host '  This script will set up CodeCompass on your machine.'
Write-Host '  It creates a virtual environment, installs dependencies,'
Write-Host '  and configures GitHub Copilot authentication.'
Write-Host ''

# -- Step 1: Check Python ---------------------------------------
Write-Header 'Step 1/5 - Checking Python'

$PythonCmd = $null
foreach ($cmd in @('python', 'python3', 'py')) {
    try {
        $verOutput = & $cmd --version 2>&1
        if ($verOutput -match '(\d+)\.(\d+)') {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $PythonCmd = $cmd
                Write-Ok "Found $cmd ($verOutput)"
                break
            }
            Write-Warn "$cmd is version $major.$minor (need 3.10+)"
        }
    } catch {
        # command not found
    }
}

if (-not $PythonCmd) {
    Write-Fail 'Python 3.10+ is required but not found.'
    Write-Host ''
    Write-Host '  Install Python from: https://www.python.org/downloads/'
    Write-Host '  Make sure to check "Add Python to PATH" during installation.'
    exit 1
}

# -- Step 2: Check Git ------------------------------------------
Write-Header 'Step 2/5 - Checking Git'

try {
    $gitVersion = & git --version 2>&1
    Write-Ok "Found $gitVersion"
} catch {
    Write-Fail 'Git is required but not found.'
    Write-Host ''
    Write-Host '  Install Git from: https://git-scm.com/downloads'
    exit 1
}

# -- Step 3: Virtual Environment --------------------------------
Write-Header 'Step 3/5 - Virtual Environment'

$VenvDir = Join-Path $ScriptDir '.venv'

if (Test-Path $VenvDir) {
    Write-Ok 'Virtual environment already exists at .venv\'
    $recreate = Read-Host '  Recreate it? [y/N]'
    if ($recreate -match '^[Yy]$') {
        Write-Info 'Removing existing virtual environment...'
        Remove-Item $VenvDir -Recurse -Force
        Write-Info 'Creating new virtual environment...'
        & $PythonCmd -m venv $VenvDir
        Write-Ok 'Virtual environment created'
    } else {
        Write-Ok 'Keeping existing virtual environment'
    }
} else {
    Write-Info 'Creating virtual environment...'
    & $PythonCmd -m venv $VenvDir
    Write-Ok 'Virtual environment created at .venv\'
}

$ActivateScript = Join-Path $VenvDir 'Scripts\Activate.ps1'
if (-not (Test-Path $ActivateScript)) {
    Write-Fail "Could not find activation script at $ActivateScript"
    exit 1
}

try {
    & $ActivateScript
    Write-Ok 'Virtual environment activated'
} catch {
    Write-Warn 'Could not activate venv via script. Using direct paths instead.'
}

$PythonExe = Join-Path $VenvDir 'Scripts\python.exe'
$CodeCompassExe = Join-Path $VenvDir 'Scripts\codecompass.exe'

# -- Step 4: Install CodeCompass -------------------------------
Write-Header 'Step 4/5 - Installing CodeCompass'

Write-Info 'Upgrading pip...'
& $PythonExe -m pip install --upgrade pip --quiet 2>$null
Write-Ok 'pip upgraded'

Write-Info 'Installing CodeCompass and dependencies...'
& $PythonExe -m pip install -e . --quiet 2>$null
Write-Ok 'CodeCompass installed'

try {
    $version = & $CodeCompassExe --version 2>&1
    Write-Ok "codecompass $version"
} catch {
    Write-Warn 'Could not verify installation'
}

# -- Step 5: Copilot Authentication -----------------------------
Write-Header 'Step 5/5 - GitHub Copilot Authentication'

$CopilotBin = $null

# Prefer bundled Copilot CLI from Python package
try {
    $CopilotPythonLines = @(
        'import copilot, pathlib, sys'
        'bin_dir = pathlib.Path(copilot.__file__).parent / "bin"'
        'for name in ["copilot.exe", "copilot"]:'
        '    p = bin_dir / name'
        '    if p.exists():'
        '        print(p)'
        '        sys.exit(0)'
        'print("")'
    )
    $CopilotProbeCode = [string]::Join("`n", $CopilotPythonLines)
    $CopilotBin = & $PythonExe -c $CopilotProbeCode 2>$null
    if ($CopilotBin) {
        $CopilotBin = $CopilotBin.ToString().Trim()
    }
} catch {
    # fallback handled below
}

# Fallback to PATH (handles fnm/nvm and global installs)
if (-not $CopilotBin -or -not (Test-Path $CopilotBin)) {
    $copilotCmd = Get-Command copilot -ErrorAction SilentlyContinue
    if ($copilotCmd -and $copilotCmd.Source -and (Test-Path $copilotCmd.Source)) {
        $CopilotBin = $copilotCmd.Source
        Write-Ok "Found Copilot CLI in PATH: $CopilotBin"
    }
}

if (-not $CopilotBin -or -not (Test-Path $CopilotBin)) {
    Write-Warn 'Could not find Copilot CLI binary (bundled or PATH).'
    Write-Warn 'You may need to authenticate manually later.'
} else {
    Write-Ok "Using Copilot CLI: $CopilotBin"
    Write-Host ''
    Write-Host '  CodeCompass needs to authenticate with GitHub Copilot.'
    Write-Host '  This uses OAuth device-flow (opens your browser).'
    Write-Host ''

    $doAuth = Read-Host '  Authenticate now? [Y/n]'
    if ($doAuth -notmatch '^[Nn]$') {
        Write-Info 'Starting Copilot login...'
        Write-Host ''
        & $CopilotBin login
        Write-Host ''
        Write-Ok 'Authentication complete'
    } else {
        Write-Warn 'Skipped authentication. Run later:'
        Write-Host "    & `"$CopilotBin`" login"
    }
}

# -- Done --------------------------------------------------------
Write-Header 'Setup Complete!'

Write-Host ''
Write-Host '  Getting Started:' -ForegroundColor White
Write-Host ''
Write-Host '  # Activate the virtual environment' -ForegroundColor Cyan
Write-Host '  .\.venv\Scripts\Activate.ps1'
Write-Host ''
Write-Host '  # Scan and onboard a repository' -ForegroundColor Cyan
Write-Host '  codecompass --repo C:\path\to\repo onboard'
Write-Host ''
Write-Host '  # Start interactive chat' -ForegroundColor Cyan
Write-Host '  codecompass --repo C:\path\to\repo chat'
Write-Host ''
Write-Host '  # Launch the full TUI' -ForegroundColor Cyan
Write-Host '  codecompass --repo C:\path\to\repo tui'
Write-Host ''
Write-Host '  # Ask a question about any codebase' -ForegroundColor Cyan
Write-Host '  codecompass --repo C:\path\to\repo ask "How does authentication work?"'
Write-Host ''
Write-Host '  # Export onboarding docs' -ForegroundColor Cyan
Write-Host '  codecompass --repo C:\path\to\repo export --format markdown -o onboarding.md'
Write-Host ''
Write-Host '  Run ' -NoNewline
Write-Host 'codecompass --help' -ForegroundColor White -NoNewline
Write-Host ' for all commands.'
Write-Host ''
