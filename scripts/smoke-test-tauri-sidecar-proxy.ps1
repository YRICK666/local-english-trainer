[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ResourceRoot = Join-Path $ProjectRoot 'src-tauri\target\debug'
$DesktopExe = Join-Path $ResourceRoot 'local-english-trainer-desktop.exe'
$TempPrefix = 'local-english-trainer-p2_5c-'
$StartedDesktop = $null

function Get-ProcessIds([string]$Name) {
    return @(
        Get-Process -Name $Name -ErrorAction SilentlyContinue |
            ForEach-Object { [int]$_.Id }
    )
}

function Get-NewProcessIds([string]$Name, [int[]]$Before) {
    $known = [Collections.Generic.HashSet[int]]::new()
    foreach ($id in $Before) { [void]$known.Add($id) }
    return @(Get-ProcessIds $Name | Where-Object { -not $known.Contains($_) })
}

function Get-P2CTemporaryRoots {
    return @(
        Get-ChildItem -LiteralPath ([IO.Path]::GetTempPath()) -Directory -Filter "$TempPrefix*" -ErrorAction Stop |
            Select-Object -ExpandProperty Name
    )
}

function Get-SafeMarkers($ErrorTask, $OutputTask) {
    $text = "$($ErrorTask.GetAwaiter().GetResult())`n$($OutputTask.GetAwaiter().GetResult())"
    return @(
        $text -split "`r?`n" |
            Where-Object { $_ -match '^(LET_LIFECYCLE_|LET_PROXY_READING_PACKS_|LOCAL_ENGLISH_TRAINER_SIDECAR_(READY|HEALTH_OK))' }
    )
}

function Assert-RequiredMarker([string[]]$Markers, [string]$Pattern) {
    if (-not ($Markers | Where-Object { $_ -match $Pattern })) {
        throw "Required proxy smoke marker is missing: $Pattern"
    }
}

$desktopBefore = Get-ProcessIds 'local-english-trainer-desktop'
$sidecarBefore = Get-ProcessIds 'local-english-trainer-api'
$rootsBefore = Get-P2CTemporaryRoots

try {
    if (-not (Test-Path -LiteralPath $DesktopExe -PathType Leaf)) { throw 'Debug desktop executable is missing.' }
    if (-not (Test-Path -LiteralPath (Join-Path $ResourceRoot 'sidecar\local-english-trainer-api\local-english-trainer-api.exe') -PathType Leaf)) {
        throw 'Debug resource tree does not contain the onedir sidecar executable.'
    }

    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $DesktopExe
    $psi.WorkingDirectory = $ResourceRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardOutput = $true
    $psi.Environment['LOCAL_ENGLISH_TRAINER_SIDECAR_LIFECYCLE_PROBE'] = '1'
    $psi.Environment['LOCAL_ENGLISH_TRAINER_PROXY_PROBE'] = '1'

    $StartedDesktop = [Diagnostics.Process]::new()
    $StartedDesktop.StartInfo = $psi
    if (-not $StartedDesktop.Start()) { throw 'Proxy smoke desktop launch returned false.' }
    $errorTask = $StartedDesktop.StandardError.ReadToEndAsync()
    $outputTask = $StartedDesktop.StandardOutput.ReadToEndAsync()

    if (-not $StartedDesktop.WaitForExit(45000)) { throw 'Proxy smoke desktop process did not exit within 45 seconds.' }
    $StartedDesktop.WaitForExit()
    $markers = Get-SafeMarkers $errorTask $outputTask
    $markers | Write-Output
    if ($StartedDesktop.ExitCode -ne 0) { throw "Proxy smoke desktop exit code $($StartedDesktop.ExitCode), expected 0." }

    Assert-RequiredMarker $markers '^LOCAL_ENGLISH_TRAINER_SIDECAR_READY$'
    Assert-RequiredMarker $markers '^LOCAL_ENGLISH_TRAINER_SIDECAR_HEALTH_OK$'
    Assert-RequiredMarker $markers '^LET_LIFECYCLE_READY$'
    Assert-RequiredMarker $markers '^LET_PROXY_READING_PACKS_OK count=\d+$'
    Assert-RequiredMarker $markers '^LET_LIFECYCLE_SHUTDOWN_HTTP_OK$'
    Assert-RequiredMarker $markers '^LET_LIFECYCLE_GRACEFUL_SHUTDOWN_OK$'
    Assert-RequiredMarker $markers '^LET_LIFECYCLE_EXIT_REQUESTED$'
    if ($markers -contains 'LET_PROXY_READING_PACKS_FAILED') { throw 'Proxy smoke emitted the safe failure marker.' }

    $newDesktop = Get-NewProcessIds 'local-english-trainer-desktop' $desktopBefore
    $newSidecars = Get-NewProcessIds 'local-english-trainer-api' $sidecarBefore
    $newRoots = @(Get-P2CTemporaryRoots | Where-Object { $_ -notin $rootsBefore })
    if ($newDesktop.Count -ne 0) { throw 'Proxy smoke left a new desktop process running.' }
    if ($newSidecars.Count -ne 0) { throw 'Proxy smoke left a new sidecar process or loopback listener running.' }
    if ($newRoots.Count -ne 0) { throw 'Proxy smoke left a lifecycle temporary root.' }
    Write-Output 'TAURI_SIDECAR_PROXY_SMOKE PASS'
} finally {
    if ($null -ne $StartedDesktop) {
        if (-not $StartedDesktop.HasExited) {
            $StartedDesktop.Kill($true)
            $StartedDesktop.WaitForExit()
        }
        $StartedDesktop.Dispose()
    }
    foreach ($pid in (Get-NewProcessIds 'local-english-trainer-api' $sidecarBefore)) {
        $sidecar = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($null -ne $sidecar -and -not $sidecar.HasExited) {
            $sidecar.Kill()
            $sidecar.WaitForExit()
        }
    }
}