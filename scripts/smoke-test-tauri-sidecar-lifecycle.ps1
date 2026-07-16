[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ResourceRoot = Join-Path $ProjectRoot 'src-tauri\target\debug'
$DesktopExe = Join-Path $ResourceRoot 'local-english-trainer-desktop.exe'
$TempPrefix = 'local-english-trainer-p2_5c-'
$RunTempRoot = Join-Path ([IO.Path]::GetTempPath()) ("let-c3-smoke-" + [Guid]::NewGuid().ToString('N'))
$StartedProcesses = [Collections.Generic.List[Diagnostics.Process]]::new()
$TrackedSidecarPids = [Collections.Generic.HashSet[int]]::new()

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

function Get-ListenerPids1420 {
    try {
        return @(
            Get-NetTCPConnection -State Listen -LocalPort 1420 -ErrorAction Stop |
                Select-Object -ExpandProperty OwningProcess -Unique
        )
    } catch {
        $lines = & "$env:SystemRoot\System32\netstat.exe" -ano -p tcp
        $pids = @(
            $lines |
                Where-Object { $_ -match '^\s*TCP\s+\S+:1420\s+\S+\s+LISTENING\s+(\d+)\s*$' } |
                ForEach-Object { [int]$Matches[1] } |
                Select-Object -Unique
        )
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect loopback port 1420 listeners: $($_.Exception.Message)" }
        return $pids
    }
}

function Get-NewApplicationCrashEvents([datetime]$Since) {
    try {
        return @(
            Get-WinEvent -FilterHashtable @{ LogName = 'Application'; StartTime = $Since } -ErrorAction Stop |
                Where-Object { $_.ProviderName -in @('Application Error', 'Windows Error Reporting') } |
                Select-Object -First 10
        )
    } catch {
        if ($_.Exception.Message -match 'No events were found') { return @() }
        throw "Could not inspect Windows Application events: $($_.Exception.Message)"
    }
}

function Get-SafeMarkers($ErrorTask, $OutputTask) {
    $text = "$($ErrorTask.GetAwaiter().GetResult())`n$($OutputTask.GetAwaiter().GetResult())"
    return @(
        $text -split "`r?`n" |
            Where-Object {
                $_ -match '^(LET_LIFECYCLE_|LOCAL_ENGLISH_TRAINER_SIDECAR_(READY|HEALTH_OK))'
            }
    )
}

function Wait-ForLifecycleLaunch([Diagnostics.Process]$Process, [int[]]$SidecarsBefore, [string[]]$RootsBefore) {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) { throw "Desktop process exited before starting the lifecycle child; exit code $($Process.ExitCode)." }
        $newRoots = @(Get-P2CTemporaryRoots | Where-Object { $_ -notin $RootsBefore })
        $newSidecars = Get-NewProcessIds 'local-english-trainer-api' $SidecarsBefore
        if ($newRoots.Count -gt 0 -and $newSidecars.Count -gt 0) {
            Start-Sleep -Milliseconds 750
            return [PSCustomObject]@{ Roots = $newRoots; Sidecars = $newSidecars }
        }
        Start-Sleep -Milliseconds 100
    }
    throw 'Lifecycle probe did not start a temporary-root sidecar within 30 seconds.'
}

function Wait-ForUnexpectedChildExit([Diagnostics.Process]$Process, [int[]]$SidecarsBefore, [string[]]$Roots) {
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) { throw "Desktop process exited before supervisor handling; exit code $($Process.ExitCode)." }
        $sidecarGone = (Get-NewProcessIds 'local-english-trainer-api' $SidecarsBefore).Count -eq 0
        $rootsGone = @(Get-P2CTemporaryRoots | Where-Object { $_ -in $Roots }).Count -eq 0
        if ($sidecarGone -and $rootsGone) {
            Start-Sleep -Milliseconds 300
            return
        }
        Start-Sleep -Milliseconds 100
    }
    throw 'Unexpected-child mode did not complete supervisor cleanup without restarting the sidecar.'
}
function Wait-ForWindow([Diagnostics.Process]$Process) {
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) { throw "Desktop process exited before creating its window; exit code $($Process.ExitCode)." }
        $Process.Refresh()
        if ($Process.MainWindowHandle -ne [IntPtr]::Zero) { return }
        Start-Sleep -Milliseconds 100
    }
    throw 'Desktop process did not create a main window handle.'
}

function Close-TrackedWindow([Diagnostics.Process]$Process) {
    $Process.Refresh()
    if ($Process.MainWindowHandle -eq [IntPtr]::Zero) { throw 'Desktop main window handle is unavailable for CloseMainWindow.' }
    if (-not $Process.CloseMainWindow()) { throw 'CloseMainWindow returned false.' }
}

function Wait-ForExitCodeZero([Diagnostics.Process]$Process, [int]$TimeoutSeconds) {
    if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) { throw "Desktop process did not exit within $TimeoutSeconds seconds." }
    $Process.WaitForExit()
    if ($Process.ExitCode -ne 0) { throw "Desktop process exited with code $($Process.ExitCode), expected 0." }
}

function Assert-Markers([string[]]$Markers, [string[]]$Required, [string[]]$Forbidden) {
    foreach ($marker in $Required) {
        if ($Markers -notcontains $marker) { throw "Required lifecycle marker is missing: $marker" }
    }
    foreach ($marker in $Forbidden) {
        if ($Markers -contains $marker) { throw "Unexpected lifecycle marker was emitted: $marker" }
    }
}

function Start-Desktop([string]$Name, [string]$FaultMode) {
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $DesktopExe
    $psi.WorkingDirectory = $ResourceRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardOutput = $true
    $psi.Environment['LOCAL_ENGLISH_TRAINER_SIDECAR_LIFECYCLE_PROBE'] = '1'
    if ($FaultMode) { $psi.Environment['LOCAL_ENGLISH_TRAINER_LIFECYCLE_FAULT'] = $FaultMode }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $psi
    if (-not $process.Start()) { throw "Desktop launch returned false for $Name." }
    $errorTask = $process.StandardError.ReadToEndAsync()
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    [void]$StartedProcesses.Add($process)
    return [PSCustomObject]@{ Process = $process; ErrorTask = $errorTask; OutputTask = $outputTask }
}
function Invoke-LifecycleCase([string]$Name, [string]$FaultMode, [string[]]$Required, [string[]]$Forbidden) {
    $beforeRoots = Get-P2CTemporaryRoots
    $beforeSidecars = Get-ProcessIds 'local-english-trainer-api'
    $run = Start-Desktop $Name $FaultMode
    try {
        Wait-ForWindow $run.Process
        $launch = Wait-ForLifecycleLaunch $run.Process $beforeSidecars $beforeRoots
        foreach ($id in $launch.Sidecars) { [void]$TrackedSidecarPids.Add($id) }
        if ($FaultMode -eq 'terminate-child-after-ready') {
            Wait-ForUnexpectedChildExit $run.Process $beforeSidecars $launch.Roots
        }
        Close-TrackedWindow $run.Process
        Wait-ForExitCodeZero $run.Process 30
        $markers = Get-SafeMarkers $run.ErrorTask $run.OutputTask
        Assert-Markers $markers $Required $Forbidden
        $remainingRoots = @(Get-P2CTemporaryRoots | Where-Object { $_ -in $launch.Roots })
        if ($remainingRoots.Count -ne 0) { throw 'Lifecycle-owned temporary root remains after desktop exit.' }
        if ((Get-NewProcessIds 'local-english-trainer-api' $beforeSidecars).Count -ne 0) { throw 'Lifecycle run left a sidecar process running.' }
        Write-Output "LET_SMOKE_LIFECYCLE_CASE_PASS=$Name"
    } finally {
        if (-not $run.Process.HasExited) {
            $run.Process.Kill($true)
            $run.Process.WaitForExit()
        }
    }
}
function Invoke-NormalModeCase {
    $beforeRoots = Get-P2CTemporaryRoots
    $beforeSidecars = Get-ProcessIds 'local-english-trainer-api'
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $DesktopExe
    $psi.WorkingDirectory = $ResourceRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardOutput = $true
    [void]$psi.Environment.Remove('LOCAL_ENGLISH_TRAINER_SIDECAR_LIFECYCLE_PROBE')
    [void]$psi.Environment.Remove('LOCAL_ENGLISH_TRAINER_LIFECYCLE_FAULT')
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $psi
    if (-not $process.Start()) { throw 'Normal desktop launch returned false.' }
    $errorTask = $process.StandardError.ReadToEndAsync()
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    [void]$StartedProcesses.Add($process)
    try {
        Wait-ForWindow $process
        Start-Sleep -Milliseconds 500
        Close-TrackedWindow $process
        Wait-ForExitCodeZero $process 20
        if ((Get-P2CTemporaryRoots | Where-Object { $_ -notin $beforeRoots }).Count -ne 0) { throw 'Normal mode created a P2.5-C temporary root.' }
        if ((Get-NewProcessIds 'local-english-trainer-api' $beforeSidecars).Count -ne 0) { throw 'Normal mode started a sidecar.' }
        if ((Get-SafeMarkers $errorTask $outputTask | Where-Object { $_ -like 'LET_LIFECYCLE_*' }).Count -ne 0) { throw 'Normal mode emitted lifecycle markers.' }
        Write-Output 'LET_SMOKE_LIFECYCLE_NORMAL_MODE_PASS'
    } finally {
        if (-not $process.HasExited) {
            $process.Kill($true)
            $process.WaitForExit()
        }
    }
}
$desktopBefore = Get-ProcessIds 'local-english-trainer-desktop'
$sidecarBefore = Get-ProcessIds 'local-english-trainer-api'
$probeBefore = Get-ProcessIds 'sidecar_startup_probe'
$webViewBefore = Get-ProcessIds 'msedgewebview2'
$listenerBefore = Get-ListenerPids1420
$temporaryRootsBefore = Get-P2CTemporaryRoots
$startedAt = Get-Date

try {
    if (-not (Test-Path -LiteralPath $DesktopExe -PathType Leaf)) { throw 'Debug desktop executable is missing.' }
    if (-not (Test-Path -LiteralPath (Join-Path $ResourceRoot 'sidecar\local-english-trainer-api\local-english-trainer-api.exe') -PathType Leaf)) { throw 'Debug resource tree does not contain the onedir sidecar executable.' }
    New-Item -ItemType Directory -Path $RunTempRoot -Force | Out-Null

    1..3 | ForEach-Object { Invoke-LifecycleCase "graceful-$_.".TrimEnd('.') '' @('LET_LIFECYCLE_READY','LET_LIFECYCLE_SHUTDOWN_HTTP_OK','LET_LIFECYCLE_GRACEFUL_SHUTDOWN_OK') @('LET_LIFECYCLE_FORCED_CLEANUP_OK','LET_LIFECYCLE_CHILD_EXITED_UNEXPECTEDLY') }
    1..2 | ForEach-Object { Invoke-LifecycleCase "unexpected-$_.".TrimEnd('.') 'terminate-child-after-ready' @('LET_LIFECYCLE_READY','LET_LIFECYCLE_CHILD_EXITED_UNEXPECTEDLY') @('LET_LIFECYCLE_GRACEFUL_SHUTDOWN_OK','LET_LIFECYCLE_FORCED_CLEANUP_OK') }
    1..2 | ForEach-Object { Invoke-LifecycleCase "fallback-$_.".TrimEnd('.') 'force-shutdown-timeout' @('LET_LIFECYCLE_READY','LET_LIFECYCLE_FORCED_CLEANUP_OK') @('LET_LIFECYCLE_SHUTDOWN_HTTP_OK','LET_LIFECYCLE_GRACEFUL_SHUTDOWN_OK') }
    Invoke-NormalModeCase

    $newListenerPids = @(Get-ListenerPids1420 | Where-Object { $_ -notin $listenerBefore })
    if ($newListenerPids.Count -ne 0) { throw 'Smoke created a new listener on port 1420.' }
    foreach ($check in @(
        @{ Name = 'local-english-trainer-desktop'; Before = $desktopBefore },
        @{ Name = 'local-english-trainer-api'; Before = $sidecarBefore },
        @{ Name = 'sidecar_startup_probe'; Before = $probeBefore },
        @{ Name = 'msedgewebview2'; Before = $webViewBefore }
    )) {
        if ((Get-NewProcessIds $check.Name $check.Before).Count -ne 0) { throw "Smoke left a new $($check.Name) process." }
    }
    if ((Get-P2CTemporaryRoots | Where-Object { $_ -notin $temporaryRootsBefore }).Count -ne 0) { throw 'Smoke left a new P2.5-C temporary root.' }
    if ((Get-NewApplicationCrashEvents $startedAt).Count -ne 0) { throw 'Smoke observed a new Application Error or Windows Error Reporting event.' }
    Write-Output 'TAURI_SIDECAR_LIFECYCLE_SMOKE PASS'
    Write-Warning 'Window handles and clean exits were automated. Visual page content still requires interactive human confirmation.'
} finally {
    foreach ($process in $StartedProcesses) {
        if (-not $process.HasExited) {
            $process.Kill($true)
            $process.WaitForExit()
        }
        $process.Dispose()
    }
    if (Test-Path -LiteralPath $RunTempRoot) { Remove-Item -LiteralPath $RunTempRoot -Recurse -Force }
}