[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$resourceRoot = [IO.Path]::GetFullPath((Join-Path $root 'src-tauri\target\debug'))
$probeExe = Join-Path $resourceRoot 'sidecar_startup_probe.exe'
if (-not (Test-Path -LiteralPath $probeExe -PathType Leaf)) { throw 'Headless startup probe executable is missing.' }

$webViewBefore = [Collections.Generic.HashSet[int]]::new()
Get-Process -Name 'msedgewebview2' -ErrorAction SilentlyContinue | ForEach-Object { [void]$webViewBefore.Add($_.Id) }
$desktopBefore = [Collections.Generic.HashSet[int]]::new()
Get-Process -Name 'local-english-trainer-desktop' -ErrorAction SilentlyContinue | ForEach-Object { [void]$desktopBefore.Add($_.Id) }

$psi = [Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $probeExe
$psi.WorkingDirectory = $resourceRoot
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true
[void]$psi.ArgumentList.Add('--resource-root')
[void]$psi.ArgumentList.Add($resourceRoot)

$p = [Diagnostics.Process]::new()
$p.StartInfo = $psi
if (-not $p.Start()) { throw 'Direct headless probe launch returned false.' }
$probePid = $p.Id
if ((Get-Process -Id $probePid -ErrorAction Stop).ProcessName -ne 'sidecar_startup_probe') { throw 'Direct PID is not the headless startup probe.' }
$outTask = $p.StandardOutput.ReadToEndAsync()
$errTask = $p.StandardError.ReadToEndAsync()
Write-Output "LET_SMOKE_HEADLESS_PID=$probePid"
try {
    if (-not $p.WaitForExit(30000)) { throw "Headless sidecar probe timed out; PID=$probePid HasExited=$($p.HasExited)" }
    $p.WaitForExit()
    $out = "$($outTask.GetAwaiter().GetResult())`n$($errTask.GetAwaiter().GetResult())"
    if ($p.ExitCode -ne 0) { throw "Headless sidecar probe exit code $($p.ExitCode): $out" }
    $markers = $out -split "`r?`n" | Where-Object { $_ -match '^(LOCAL_ENGLISH_TRAINER_SIDECAR_|LET_HEALTH_HTTP_DIAG )' }
    $markers | Write-Output
    foreach ($marker in @('LOCAL_ENGLISH_TRAINER_SIDECAR_READY','LOCAL_ENGLISH_TRAINER_SIDECAR_HEALTH_OK','LOCAL_ENGLISH_TRAINER_SIDECAR_CLEANUP_COMPLETE','LOCAL_ENGLISH_TRAINER_SIDECAR_STARTUP_PROBE_HEADLESS','LOCAL_ENGLISH_TRAINER_SIDECAR_STARTUP_PROBE success')) {
        if ($out -notmatch [regex]::Escape($marker)) { throw "Required marker missing: $marker" }
    }
    $newWebView = @(Get-Process -Name 'msedgewebview2' -ErrorAction SilentlyContinue | Where-Object { -not $webViewBefore.Contains($_.Id) })
    $newDesktop = @(Get-Process -Name 'local-english-trainer-desktop' -ErrorAction SilentlyContinue | Where-Object { -not $desktopBefore.Contains($_.Id) })
    if ($newWebView.Count -ne 0) { throw 'Headless probe created a new WebView2 process.' }
    if ($newDesktop.Count -ne 0) { throw 'Headless probe created a Tauri desktop process.' }
    Write-Output "LET_SMOKE_HEADLESS_EXIT_CODE=$($p.ExitCode)"
    Write-Output 'TAURI_SIDECAR_HEADLESS_STARTUP_SMOKE PASS'
} finally {
    if (-not $p.HasExited) { $p.Kill($true); $p.WaitForExit() }
    $p.Dispose()
}