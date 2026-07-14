[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$StageScript = Join-Path $PSScriptRoot 'stage-sidecar-resource.ps1'
$TestRoot = Join-Path $env:TEMP "local-english-trainer-p2_5a-$([Guid]::NewGuid().ToString('N'))"
$Passed = 0
$Failed = 0
$Skipped = 0

function Write-FixtureFile([string]$RelativePath, [string]$Content = 'fixture') {
    $path = Join-Path $FixtureSource $RelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    [IO.File]::WriteAllText($path, $Content, [Text.UTF8Encoding]::new($false))
}

function Get-ManifestLines([string]$Root) {
    return @(
        Get-ChildItem -LiteralPath $Root -File -Force -Recurse |
            Where-Object { $_.Name -ne '.local-english-trainer-resource-stage.json' } |
            ForEach-Object { "{0}|{1}" -f [IO.Path]::GetRelativePath($Root, $_.FullName).Replace('\', '/'), $_.Length } |
            Sort-Object
    )
}

function Invoke-Pass([string]$Name, [scriptblock]$Action) {
    try {
        & $Action
        $script:Passed++
        Write-Output "PASS $Name"
    } catch {
        $script:Failed++
        Write-Output "FAIL ${Name}: $($_.Exception.Message)"
    }
}

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Assert-StageFailure([string]$Name, [scriptblock]$Action) {
    $failedAsExpected = $false
    try { & $Action } catch { $failedAsExpected = $true }
    Assert-True $failedAsExpected "$Name was accepted unexpectedly."
}

try {
    New-Item -ItemType Directory -Path $TestRoot | Out-Null
    $FixtureSource = Join-Path $TestRoot 'fixture-source'
    $Destination = Join-Path $TestRoot 'staged-sidecar'
    New-Item -ItemType Directory -Path $FixtureSource | Out-Null
    Write-FixtureFile 'local-english-trainer-api.exe' 'placeholder executable; never executed'
    Write-FixtureFile '_internal/python-runtime.dll' 'runtime'
    Write-FixtureFile '_internal/nested/module.pyd' 'nested module'
    Write-FixtureFile 'assets/file with spaces.txt' 'spaces'
    Write-FixtureFile 'assets/中文文件.txt' 'unicode'
    [IO.File]::WriteAllBytes((Join-Path $FixtureSource 'empty-file.dat'), [byte[]]@())

    Invoke-Pass 'first complete recursive copy' {
        & $StageScript -SourceDir $FixtureSource -DestinationDir $Destination
        Assert-True (Test-Path -LiteralPath (Join-Path $Destination '_internal\nested\module.pyd')) 'Nested _internal file is missing.'
        Assert-True (Test-Path -LiteralPath (Join-Path $Destination 'assets\file with spaces.txt')) 'Space filename is missing.'
        Assert-True (Test-Path -LiteralPath (Join-Path $Destination 'assets\中文文件.txt')) 'Unicode filename is missing.'
        Assert-True ((Get-Item -LiteralPath (Join-Path $Destination 'empty-file.dat')).Length -eq 0) 'Empty file size changed.'
        Assert-True ((Compare-Object (Get-ManifestLines $FixtureSource) (Get-ManifestLines $Destination)).Count -eq 0) 'Source and destination manifests differ.'
    }

    Invoke-Pass 'stale files are removed on repeat staging' {
        Write-FixtureFile 'stale-file.txt' 'stale'
        & $StageScript -SourceDir $FixtureSource -DestinationDir $Destination
        Remove-Item -LiteralPath (Join-Path $FixtureSource 'stale-file.txt') -Force
        & $StageScript -SourceDir $FixtureSource -DestinationDir $Destination
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $Destination 'stale-file.txt'))) 'Stale destination file remained.'
    }

    Invoke-Pass 'source updates synchronize by path and size' {
        Write-FixtureFile 'assets/file with spaces.txt' 'updated fixture content with a different size'
        & $StageScript -SourceDir $FixtureSource -DestinationDir $Destination
        Assert-True ((Get-Item -LiteralPath (Join-Path $FixtureSource 'assets\file with spaces.txt')).Length -eq (Get-Item -LiteralPath (Join-Path $Destination 'assets\file with spaces.txt')).Length) 'Updated file size did not synchronize.'
        Assert-True ((Compare-Object (Get-ManifestLines $FixtureSource) (Get-ManifestLines $Destination)).Count -eq 0) 'Updated manifests differ.'
    }

    Invoke-Pass 'missing root exe is rejected' {
        $missingExe = Join-Path $TestRoot 'missing-exe'
        New-Item -ItemType Directory -Path $missingExe | Out-Null
        Assert-StageFailure 'Missing root exe' { & $StageScript -SourceDir $missingExe -DestinationDir (Join-Path $TestRoot 'missing-exe-destination') }
    }

    Invoke-Pass 'file source is rejected' {
        Assert-StageFailure 'File source' { & $StageScript -SourceDir (Join-Path $FixtureSource 'local-english-trainer-api.exe') -DestinationDir (Join-Path $TestRoot 'file-source-destination') }
    }

    foreach ($extension in @('db', 'sqlite', 'sqlite3')) {
        Invoke-Pass "database extension .$extension is rejected" {
            $forbiddenPath = Join-Path $FixtureSource "forbidden.$extension"
            [IO.File]::WriteAllText($forbiddenPath, 'not a database', [Text.UTF8Encoding]::new($false))
            try {
                Assert-StageFailure "Database extension .$extension" { & $StageScript -SourceDir $FixtureSource -DestinationDir (Join-Path $TestRoot "database-$extension-destination") }
            } finally {
                Remove-Item -LiteralPath $forbiddenPath -Force
            }
        }
    }

    Invoke-Pass 'equal source and destination is rejected' {
        Assert-StageFailure 'Equal paths' { & $StageScript -SourceDir $FixtureSource -DestinationDir $FixtureSource }
    }

    Invoke-Pass 'destination inside source is rejected' {
        Assert-StageFailure 'Nested destination' { & $StageScript -SourceDir $FixtureSource -DestinationDir (Join-Path $FixtureSource 'nested-destination') }
    }

    Invoke-Pass 'reparse point is rejected' {
        $outside = Join-Path $TestRoot 'junction-target'
        $junction = Join-Path $FixtureSource 'linked-directory'
        New-Item -ItemType Directory -Path $outside | Out-Null
        New-Item -ItemType Junction -Path $junction -Target $outside | Out-Null
        $junctionItem = Get-Item -LiteralPath $junction -Force
        Assert-True (($junctionItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) 'Junction fixture was not recognized as a ReparsePoint.'
        try {
            Assert-StageFailure 'Junction source entry' { & $StageScript -SourceDir $FixtureSource -DestinationDir (Join-Path $TestRoot 'junction-destination') }
        } finally {
            Remove-Item -LiteralPath $junction -Force
        }
    }

    $outsideFile = Join-Path $TestRoot 'symbolic-link-target.txt'
    $symbolicLink = Join-Path $FixtureSource 'linked-file.txt'
    [IO.File]::WriteAllText($outsideFile, 'outside fixture', [Text.UTF8Encoding]::new($false))
    $symbolicLinkCreated = $false
    try {
        New-Item -ItemType SymbolicLink -Path $symbolicLink -Target $outsideFile | Out-Null
        $symbolicLinkCreated = $true
    } catch {
        $message = $_.Exception.Message
        $permissionDenied = $_.Exception -is [UnauthorizedAccessException] -and $message -match 'Administrator privilege required'
        if (-not $permissionDenied) { throw }
        $Skipped++
        Write-Output "SKIP symbolic link is rejected: $message"
    }
    if ($symbolicLinkCreated) {
        Invoke-Pass 'symbolic link is rejected' {
            $symbolicLinkItem = Get-Item -LiteralPath $symbolicLink -Force
            Assert-True (($symbolicLinkItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) 'Symbolic-link fixture was not recognized as a ReparsePoint.'
            try {
                Assert-StageFailure 'Symbolic link source entry' { & $StageScript -SourceDir $FixtureSource -DestinationDir (Join-Path $TestRoot 'symbolic-link-destination') }
            } finally {
                Remove-Item -LiteralPath $symbolicLink -Force
            }
        }
    }

    Invoke-Pass 'unmanaged nonempty destination is rejected' {
        $unmanaged = Join-Path $TestRoot 'unmanaged-destination'
        New-Item -ItemType Directory -Path $unmanaged | Out-Null
        [IO.File]::WriteAllText((Join-Path $unmanaged 'do-not-overwrite.txt'), 'unmanaged', [Text.UTF8Encoding]::new($false))
        Assert-StageFailure 'Unmanaged destination' { & $StageScript -SourceDir $FixtureSource -DestinationDir $unmanaged }
    }

    Invoke-Pass 'dry run makes no destination mutation' {
        $dryRunDestination = Join-Path $TestRoot 'dry-run-destination'
        & $StageScript -SourceDir $FixtureSource -DestinationDir $dryRunDestination
        Write-FixtureFile 'dry-run-new.txt' 'would be staged'
        try {
            & $StageScript -SourceDir $FixtureSource -DestinationDir $dryRunDestination -WhatIf
            Assert-True (-not (Test-Path -LiteralPath (Join-Path $dryRunDestination 'dry-run-new.txt'))) 'WhatIf created a new file.'
            Assert-True ((Compare-Object (Get-ManifestLines $FixtureSource) (Get-ManifestLines $dryRunDestination)).Count -ne 0) 'WhatIf unexpectedly synchronized the destination.'
        } finally {
            Remove-Item -LiteralPath (Join-Path $FixtureSource 'dry-run-new.txt') -Force
        }
    }
} finally {
    if (Test-Path -LiteralPath $TestRoot) { Remove-Item -LiteralPath $TestRoot -Recurse -Force }
}

Write-Output "RESULT Passed=$Passed Failed=$Failed Skipped=$Skipped"
if ($Failed -gt 0) { exit 1 }