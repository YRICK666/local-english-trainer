[CmdletBinding()]
param(
    [string]$PythonPath = "C:\Users\王云楷\AppData\Local\Programs\Python\Python311\python.exe",
    [switch]$RecreateVenv,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $Root ".venv-sidecar-build"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$BuildRoot = Join-Path $Root "desktop-build"
$WorkPath = Join-Path $BuildRoot "work"
$DistPath = Join-Path $BuildRoot "sidecar"
$SpecPath = Join-Path $Root "desktop\sidecar\local_english_trainer_api.spec"

function Invoke-Checked([scriptblock]$Command, [string]$FailureMessage) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
}

if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Independent CPython 3.11.5 was not found: $PythonPath" }
$probe = & $PythonPath -c "import platform,sys; print(platform.python_implementation() + '|' + platform.python_version() + '|' + sys.executable + '|' + sys.prefix)"
if ($LASTEXITCODE -ne 0 -or $probe -notmatch '^CPython\|3\.11\.5\|' -or $probe -match '(?i)conda|anaconda') {
    throw "Sidecar builds require the independent CPython 3.11.5 installation, not Conda."
}

if ($Clean -and (Test-Path -LiteralPath $BuildRoot)) {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}
if ($RecreateVenv -and (Test-Path -LiteralPath $VenvPath)) {
    Remove-Item -LiteralPath $VenvPath -Recurse -Force
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Invoke-Checked { & $PythonPath -m venv $VenvPath } "Could not create the isolated sidecar build environment."
}

Invoke-Checked { & $VenvPython -m pip install --require-hashes -r (Join-Path $Root "requirements\desktop.lock") } "Could not install desktop.lock into the sidecar build environment."
New-Item -ItemType Directory -Force -Path $WorkPath, $DistPath | Out-Null
Invoke-Checked {
    & $VenvPython -m PyInstaller --noconfirm --clean --workpath $WorkPath --distpath $DistPath $SpecPath
} "PyInstaller sidecar build failed."

$ExecutablePath = Join-Path $DistPath "local-english-trainer-api\local-english-trainer-api.exe"
if (-not (Test-Path -LiteralPath $ExecutablePath)) { throw "Sidecar executable was not produced." }
Write-Output ([IO.Path]::GetFullPath($ExecutablePath))
