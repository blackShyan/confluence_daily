param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Requirements = Join-Path $Root "requirements.txt"
$Spec = Join-Path $Root "packaging\ConfluenceDailyUploader.spec"
$Exe = Join-Path $Root "dist\ConfluenceDailyUploader\ConfluenceDailyUploader.exe"

Set-Location $Root

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

function New-LocalVenv {
    $Candidates = @(
        @{ FilePath = "py"; Arguments = @("-3.11", "-m", "venv", ".venv") },
        @{ FilePath = "py"; Arguments = @("-3", "-m", "venv", ".venv") },
        @{ FilePath = "python"; Arguments = @("-m", "venv", ".venv") }
    )

    foreach ($Candidate in $Candidates) {
        if (-not (Get-Command $Candidate.FilePath -ErrorAction SilentlyContinue)) {
            continue
        }

        $CandidateArgs = [string[]]$Candidate.Arguments
        & $Candidate.FilePath @CandidateArgs
        if ($LASTEXITCODE -eq 0) {
            return
        }
    }

    throw "Could not create .venv. Install Python 3.11 or newer and try again."
}

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "Creating .venv..."
    New-LocalVenv
}

if (-not $SkipInstall) {
    Write-Host "Installing packaging dependencies..."
    Invoke-Native $Python -m pip install --upgrade pip
    Invoke-Native $Python -m pip install -r $Requirements
}

Write-Host "Building ConfluenceDailyUploader.exe..."
Invoke-Native $Python -m PyInstaller --noconfirm --clean $Spec

if (-not (Test-Path -LiteralPath $Exe)) {
    throw "Build finished, but the expected exe was not found: $Exe"
}

Write-Host ""
Write-Host "Build complete:"
Write-Host $Exe
Write-Host ""
Write-Host "Distribute the whole dist\ConfluenceDailyUploader folder, not only the exe."
