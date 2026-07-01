param(
    [string]$Version,
    [string]$PublishPath,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Requirements = Join-Path $Root "requirements.txt"
$PyProject = Join-Path $Root "pyproject.toml"
$Spec = Join-Path $Root "packaging\ConfluenceDailyUploader.spec"
$DistFolder = Join-Path $Root "dist\ConfluenceDailyUploader"
$Exe = Join-Path $DistFolder "ConfluenceDailyUploader.exe"
$Manifest = Join-Path $Root "dist\latest.json"
$BuildVersionModule = Join-Path $Root "src\confluence_daily\_build_version.py"

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

function Get-ProjectVersion {
    $Content = Get-Content -LiteralPath $PyProject -Raw -Encoding UTF8
    $Match = [regex]::Match($Content, '(?m)^version\s*=\s*"([^"]+)"')
    if (-not $Match.Success) {
        throw "Could not read project version from $PyProject"
    }
    return $Match.Groups[1].Value
}

function Get-VersionTuple {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $CleanValue = $Value.Trim()
    if ($CleanValue.StartsWith("v", [System.StringComparison]::OrdinalIgnoreCase)) {
        $CleanValue = $CleanValue.Substring(1)
    }

    $Match = [regex]::Match($CleanValue, '^\d+(\.\d+){0,3}')
    if (-not $Match.Success) {
        throw "Version must start with numeric parts, for example 0.1.0 or 1.2.3.4. Received: $Value"
    }

    $Parts = @($Match.Value.Split(".") | ForEach-Object { [int]$_ })
    while ($Parts.Count -lt 4) {
        $Parts += 0
    }

    return $Parts[0..3]
}

function New-VersionInfoFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$BuildVersion
    )

    $VersionParts = Get-VersionTuple $BuildVersion
    $FileVersionTuple = $VersionParts -join ", "
    $SafeVersion = $BuildVersion.Replace("'", "")
    $Content = @"
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($FileVersionTuple),
    prodvers=($FileVersionTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Confluence Daily Uploader'),
          StringStruct('FileDescription', 'Confluence Daily Uploader'),
          StringStruct('FileVersion', '$SafeVersion'),
          StringStruct('InternalName', 'ConfluenceDailyUploader'),
          StringStruct('OriginalFilename', 'ConfluenceDailyUploader.exe'),
          StringStruct('ProductName', 'Confluence Daily Uploader'),
          StringStruct('ProductVersion', '$SafeVersion')
        ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@

    $Parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    Set-Content -LiteralPath $Path -Value $Content -Encoding UTF8
}

function Invoke-RobocopyMirror {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    robocopy $Source $Destination /MIR /R:3 /W:1 /NFL /NDL /NJH /NJS /NP
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -gt 7) {
        throw "Robocopy failed with exit code $ExitCode`: $Source -> $Destination"
    }
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

$BuildVersion = if ($Version) { $Version.Trim() } else { Get-ProjectVersion }
if ($BuildVersion.StartsWith("v", [System.StringComparison]::OrdinalIgnoreCase)) {
    $BuildVersion = $BuildVersion.Substring(1)
}
Get-VersionTuple $BuildVersion | Out-Null

$GeneratedDir = Join-Path ([System.IO.Path]::GetTempPath()) "ConfluenceDailyUploaderBuild"
$VersionInfoFile = Join-Path $GeneratedDir "version_info.txt"
New-VersionInfoFile -Path $VersionInfoFile -BuildVersion $BuildVersion
Set-Content -LiteralPath $BuildVersionModule -Value "__version__ = `"$BuildVersion`"" -Encoding UTF8

Write-Host "Building ConfluenceDailyUploader.exe v$BuildVersion..."
$env:CONFLUENCE_DAILY_VERSION_FILE = $VersionInfoFile
try {
    Invoke-Native $Python -m PyInstaller --noconfirm --clean $Spec
}
finally {
    Remove-Item Env:\CONFLUENCE_DAILY_VERSION_FILE -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $BuildVersionModule -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $Exe)) {
    throw "Build finished, but the expected exe was not found: $Exe"
}

$ManifestPayload = [ordered]@{
    version = $BuildVersion
    folder = "ConfluenceDailyUploader"
    notes = ""
} | ConvertTo-Json
[System.IO.File]::WriteAllText($Manifest, $ManifestPayload, [System.Text.UTF8Encoding]::new($false))

if ($PublishPath) {
    $PublishRoot = $PublishPath.Trim()
    [System.IO.Directory]::CreateDirectory($PublishRoot) | Out-Null
    $PublishDist = Join-Path $PublishRoot "ConfluenceDailyUploader"
    Invoke-RobocopyMirror -Source $DistFolder -Destination $PublishDist
    Copy-Item -LiteralPath $Manifest -Destination (Join-Path $PublishRoot "latest.json") -Force
}

Write-Host ""
Write-Host "Build complete:"
Write-Host $Exe
Write-Host $Manifest
if ($PublishPath) {
    Write-Host "Published update:"
    Write-Host $PublishPath
}
Write-Host ""
Write-Host "Version: v$BuildVersion"
Write-Host "Distribute dist\ConfluenceDailyUploader together with dist\latest.json."
