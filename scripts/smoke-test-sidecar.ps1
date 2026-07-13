[CmdletBinding()]
param(
    [switch]$Source,
    [switch]$Bundled,
    [string]$ExecutablePath
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$BuildPython = Join-Path $Root ".venv-sidecar-build\Scripts\python.exe"
$SourcePython = Join-Path $Root ".venv-p0-verify\Scripts\python.exe"
$ProjectDatabase = Join-Path $Root "data\local_english_trainer.sqlite3"

if ($Source -eq $Bundled) { throw "Specify exactly one of -Source or -Bundled." }
if ($Source -and -not (Test-Path -LiteralPath $SourcePython)) { throw "Source smoke requires the isolated .venv-p0-verify environment." }
if ($Bundled -and -not $ExecutablePath) { $ExecutablePath = Join-Path $Root "desktop-build\sidecar\local-english-trainer-api\local-english-trainer-api.exe" }
if ($Bundled -and -not (Test-Path -LiteralPath $ExecutablePath)) { throw "Bundled sidecar executable was not found." }

function Invoke-SidecarRequest([System.Net.Http.HttpClient]$Client, [string]$Method, [string]$Uri, [string]$Token = "") {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), $Uri)
    if ($Token) { $request.Headers.TryAddWithoutValidation("X-Local-English-Trainer-Token", $Token) | Out-Null }
    try {
        $response = $Client.SendAsync($request).GetAwaiter().GetResult()
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        }
    } finally {
        $request.Dispose()
    }
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("local-english-trainer-sidecar-smoke-" + [guid]::NewGuid().ToString("N"))
$userDataRoot = Join-Path $tempRoot "user-data"
$readyFile = Join-Path $tempRoot "ready\sidecar.json"
$token = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
$environmentKeys = @(
    "LOCAL_ENGLISH_TRAINER_MODE",
    "LOCAL_ENGLISH_TRAINER_USER_DATA_ROOT",
    "LOCAL_ENGLISH_TRAINER_STARTUP_TOKEN",
    "LOCAL_ENGLISH_TRAINER_READY_FILE",
    "LOCAL_ENGLISH_TRAINER_ALLOWED_ORIGINS",
    "LOCAL_ENGLISH_TRAINER_PORT",
    "LOCAL_ENGLISH_TRAINER_DATABASE_URL"
)
$originalEnvironment = @{}
$process = $null
$client = [System.Net.Http.HttpClient]::new()

try {
    foreach ($key in $environmentKeys) { $originalEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, "Process") }
    $env:LOCAL_ENGLISH_TRAINER_MODE = "desktop_production"
    $env:LOCAL_ENGLISH_TRAINER_USER_DATA_ROOT = $userDataRoot
    $env:LOCAL_ENGLISH_TRAINER_STARTUP_TOKEN = $token
    $env:LOCAL_ENGLISH_TRAINER_READY_FILE = $readyFile
    $env:LOCAL_ENGLISH_TRAINER_ALLOWED_ORIGINS = ""
    $env:LOCAL_ENGLISH_TRAINER_PORT = "0"
    Remove-Item Env:LOCAL_ENGLISH_TRAINER_DATABASE_URL -ErrorAction SilentlyContinue

    if ($Source) {
        $process = Start-Process -FilePath $SourcePython -ArgumentList @("-m", "backend.desktop_sidecar") -WorkingDirectory $Root -PassThru -WindowStyle Hidden
    } else {
        $process = Start-Process -FilePath $ExecutablePath -WorkingDirectory (Split-Path -Parent $ExecutablePath) -PassThru -WindowStyle Hidden
    }

    $readyDeadline = [DateTime]::UtcNow.AddSeconds(15)
    while (-not (Test-Path -LiteralPath $readyFile) -and [DateTime]::UtcNow -lt $readyDeadline) {
        if ($process.HasExited) { throw "Sidecar exited before becoming ready." }
        Start-Sleep -Milliseconds 100
    }
    if (-not (Test-Path -LiteralPath $readyFile)) { throw "Sidecar did not produce a ready file within 15 seconds." }
    if ($process.HasExited) { throw "Sidecar exited after writing ready." }

    $ready = Get-Content -Raw -LiteralPath $readyFile | ConvertFrom-Json
    if ($ready.status -ne "ready" -or $ready.host -ne "127.0.0.1" -or [int]$ready.port -le 0 -or $ready.run_mode -ne "desktop_production") {
        throw "Ready file did not contain a valid loopback desktop handshake."
    }
    if ($ready.PSObject.Properties.Name -contains "startup_token" -or $ready.PSObject.Properties.Name -contains "database_path") {
        throw "Ready file contains sensitive data."
    }

    $version = Get-Content -Raw -LiteralPath (Join-Path $Root "version.json") | ConvertFrom-Json
    if ($ready.app_version -ne $version.app_version -or $ready.api_protocol_version -ne $version.api_protocol_version -or $ready.schema_version -ne $version.schema_version) {
        throw "Ready file version contract does not match version.json."
    }

    $baseUri = "http://127.0.0.1:$($ready.port)"
    if ((Invoke-SidecarRequest $client "GET" "$baseUri/health").StatusCode -notin @(401, 403)) { throw "Health accepted a missing token." }
    if ((Invoke-SidecarRequest $client "GET" "$baseUri/health" ("x" * 40)).StatusCode -notin @(401, 403)) { throw "Health accepted an incorrect token." }
    $health = Invoke-SidecarRequest $client "GET" "$baseUri/health" $token
    if ($health.StatusCode -ne 200) { throw "Health did not accept the startup token." }
    $healthJson = $health.Body | ConvertFrom-Json
    if ($healthJson.app_version -ne $version.app_version -or $healthJson.api_protocol_version -ne $version.api_protocol_version -or $healthJson.schema_version -ne $version.schema_version -or $healthJson.run_mode -ne "desktop_production") {
        throw "Health version handshake did not match the ready file contract."
    }

    $shutdown = Invoke-SidecarRequest $client "POST" "$baseUri/desktop/shutdown" $token
    if ($shutdown.StatusCode -ne 200 -or (($shutdown.Body | ConvertFrom-Json).status -ne "shutting_down")) { throw "Sidecar did not accept graceful shutdown." }
    if (-not $process.WaitForExit(10000)) { throw "Sidecar did not exit within 10 seconds after shutdown." }
    if ($process.ExitCode -ne 0) { throw "Sidecar exited with a non-zero code." }
    if (Test-Path -LiteralPath $readyFile) { throw "Ready file remains after sidecar shutdown." }

    $databasePath = Join-Path $userDataRoot "data\local_english_trainer.sqlite3"
    if (-not (Test-Path -LiteralPath $databasePath)) { throw "Sidecar did not create its temporary SQLite database." }
    $IntegrityPython = if ($Source) { $SourcePython } else { $BuildPython }
    $integrity = & $IntegrityPython -c "import sqlite3,sys; row=sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone(); print(row[0]); raise SystemExit(0 if row and row[0].lower() == 'ok' else 1)" $databasePath
    if ($LASTEXITCODE -ne 0 -or $integrity -ne "ok") { throw "Temporary sidecar SQLite integrity check failed." }
    if (Test-Path -LiteralPath $ProjectDatabase) { throw "Repository development database was unexpectedly created." }
    $logFile = Join-Path $userDataRoot "logs\sidecar.log"
    if ((Get-Content -Raw -LiteralPath $logFile) -match [regex]::Escape($token)) { throw "Sidecar log contains the startup token." }

    Write-Output "sidecar smoke passed"
} finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit()
    }
    $client.Dispose()
    foreach ($key in $environmentKeys) {
        if ($null -eq $originalEnvironment[$key]) { Remove-Item "Env:$key" -ErrorAction SilentlyContinue } else { [Environment]::SetEnvironmentVariable($key, $originalEnvironment[$key], "Process") }
    }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
