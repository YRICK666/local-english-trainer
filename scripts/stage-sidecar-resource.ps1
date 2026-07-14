[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string]$SourceDir,
    [string]$DestinationDir
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$OriginalRepositoryRoot = [IO.Path]::GetFullPath('G:\AI-Workstation\local-english-trainer')
$ManagedStagingRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'desktop-build\tauri-resources'))
$DefaultDestination = Join-Path $ManagedStagingRoot 'sidecar\local-english-trainer-api'
$MarkerName = '.local-english-trainer-resource-stage.json'
$MarkerManagedBy = 'local-english-trainer.stage-sidecar-resource'
$MarkerSchemaVersion = 1

function Get-NormalizedExistingDirectory([string]$Path, [string]$Name) {
    if (-not [IO.Path]::IsPathFullyQualified($Path)) { throw "$Name must be an absolute path." }
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { throw "$Name must be an existing directory: $Path" }
    return [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path).TrimEnd('\')
}

function Get-NormalizedDestination([string]$Path) {
    if (-not [IO.Path]::IsPathFullyQualified($Path)) { throw 'DestinationDir must be an absolute path.' }
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Test-IsSameOrChildPath([string]$Candidate, [string]$Parent) {
    $comparison = [StringComparison]::OrdinalIgnoreCase
    $normalizedParent = $Parent.TrimEnd('\')
    return $Candidate.Equals($normalizedParent, $comparison) -or $Candidate.StartsWith("$normalizedParent\", $comparison)
}

function Assert-NoReparsePoints([string]$Path, [string]$Name) {
    $rootItem = Get-Item -LiteralPath $Path -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "$Name may not be a reparse point: $Path" }
    $reparsePoint = Get-ChildItem -LiteralPath $Path -Force -Recurse -ErrorAction Stop |
        Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 } |
        Select-Object -First 1
    if ($null -ne $reparsePoint) { throw "$Name contains a reparse point and cannot be staged: $($reparsePoint.FullName)" }
}

function Assert-NoDatabaseFiles([string]$Path) {
    $forbidden = Get-ChildItem -LiteralPath $Path -File -Force -Recurse -ErrorAction Stop |
        Where-Object { $_.Extension -in @('.db', '.sqlite', '.sqlite3') } |
        Select-Object -First 1
    if ($null -ne $forbidden) { throw "SourceDir contains a database-like file and cannot be staged: $($forbidden.FullName)" }
}

function Get-FileManifest([string]$Root, [string[]]$ExcludedRelativePaths = @()) {
    $excluded = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($relativePath in $ExcludedRelativePaths) { [void]$excluded.Add($relativePath.Replace('\', '/')) }
    return @(
        Get-ChildItem -LiteralPath $Root -File -Force -Recurse -ErrorAction Stop |
            ForEach-Object {
                $relativePath = [IO.Path]::GetRelativePath($Root, $_.FullName).Replace('\', '/')
                if (-not $excluded.Contains($relativePath)) { [PSCustomObject]@{ Path = $relativePath; Length = [int64]$_.Length } }
            } |
            Sort-Object Path
    )
}

function Assert-ManifestMatches([object[]]$Expected, [object[]]$Actual) {
    if ($Expected.Count -ne $Actual.Count) { throw "Staging verification failed: expected $($Expected.Count) files but found $($Actual.Count)." }
    for ($index = 0; $index -lt $Expected.Count; $index++) {
        if ($Expected[$index].Path -ne $Actual[$index].Path -or $Expected[$index].Length -ne $Actual[$index].Length) {
            throw "Staging verification failed at index ${index}: expected '$($Expected[$index].Path)' ($($Expected[$index].Length)), found '$($Actual[$index].Path)' ($($Actual[$index].Length))."
        }
    }
}

function Test-ManagedDestination([string]$Path) {
    $markerPath = Join-Path $Path $MarkerName
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) { return $false }
    try {
        $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json -ErrorAction Stop
        return $marker.managedBy -eq $MarkerManagedBy -and $marker.schemaVersion -eq $MarkerSchemaVersion
    } catch { return $false }
}

function Write-StageMarker([string]$Path, [object[]]$Manifest) {
    $marker = [ordered]@{
        schemaVersion = $MarkerSchemaVersion
        managedBy = $MarkerManagedBy
        sourceBasename = (Split-Path -Leaf $SourcePath)
        stagedFileCount = $Manifest.Count
        stagedUtc = [DateTime]::UtcNow.ToString('o')
    }
    $marker | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Path $MarkerName) -Encoding utf8NoBOM
}

if ([string]::IsNullOrWhiteSpace($DestinationDir)) { $DestinationDir = $DefaultDestination }
$SourcePath = Get-NormalizedExistingDirectory $SourceDir 'SourceDir'
$DestinationPath = Get-NormalizedDestination $DestinationDir
$TempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')

if (-not (Test-IsSameOrChildPath $DestinationPath $ManagedStagingRoot) -and -not (Test-IsSameOrChildPath $DestinationPath $TempRoot)) {
    throw "DestinationDir must be under the managed staging root or TEMP: $DestinationPath"
}
if (Test-IsSameOrChildPath $SourcePath $OriginalRepositoryRoot) { throw "SourceDir must not be under the original daily-use repository: $SourcePath" }
if ($SourcePath.Equals($DestinationPath, [StringComparison]::OrdinalIgnoreCase)) { throw 'SourceDir and DestinationDir must not be the same directory.' }
if (Test-IsSameOrChildPath $DestinationPath $SourcePath) { throw 'DestinationDir must not be inside SourceDir.' }
if (-not (Test-Path -LiteralPath (Join-Path $SourcePath 'local-english-trainer-api.exe') -PathType Leaf)) {
    throw "SourceDir must contain local-english-trainer-api.exe at its root: $SourcePath"
}
Assert-NoReparsePoints $SourcePath 'SourceDir'
Assert-NoDatabaseFiles $SourcePath

if (Test-Path -LiteralPath $DestinationPath) {
    if (-not (Test-Path -LiteralPath $DestinationPath -PathType Container)) { throw "DestinationDir must be a directory when it exists: $DestinationPath" }
    Assert-NoReparsePoints $DestinationPath 'DestinationDir'
    $destinationItems = @(Get-ChildItem -LiteralPath $DestinationPath -Force)
    if ($destinationItems.Count -gt 0 -and -not (Test-ManagedDestination $DestinationPath)) {
        throw "DestinationDir is non-empty but is not managed by this script: $DestinationPath"
    }
}

$sourceManifest = Get-FileManifest $SourcePath
if ($WhatIfPreference) {
    Write-Output "WhatIf: would stage $($sourceManifest.Count) files from '$SourcePath' to '$DestinationPath'."
    return
}

$destinationParent = Split-Path -Parent $DestinationPath
New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
$destinationLeaf = Split-Path -Leaf $DestinationPath
$temporaryPath = Join-Path $destinationParent ".${destinationLeaf}.tmp-$([Guid]::NewGuid().ToString('N'))"
$backupPath = Join-Path $destinationParent ".${destinationLeaf}.backup-$([Guid]::NewGuid().ToString('N'))"
$movedPreviousDestination = $false

try {
    New-Item -ItemType Directory -Path $temporaryPath | Out-Null
    Get-ChildItem -LiteralPath $SourcePath -Force | Copy-Item -Destination $temporaryPath -Recurse -Force
    Assert-ManifestMatches $sourceManifest (Get-FileManifest $temporaryPath)
    Write-StageMarker $temporaryPath $sourceManifest

    if (Test-Path -LiteralPath $DestinationPath) {
        Move-Item -LiteralPath $DestinationPath -Destination $backupPath -ErrorAction Stop
        $movedPreviousDestination = $true
    }
    try {
        Move-Item -LiteralPath $temporaryPath -Destination $DestinationPath -ErrorAction Stop
    } catch {
        if ($movedPreviousDestination -and -not (Test-Path -LiteralPath $DestinationPath) -and (Test-Path -LiteralPath $backupPath)) {
            Move-Item -LiteralPath $backupPath -Destination $DestinationPath -ErrorAction SilentlyContinue
        }
        throw
    }
    if ($movedPreviousDestination -and (Test-Path -LiteralPath $backupPath)) { Remove-Item -LiteralPath $backupPath -Recurse -Force }
    Assert-ManifestMatches $sourceManifest (Get-FileManifest $DestinationPath @($MarkerName))
    Write-Output "Staged $($sourceManifest.Count) files to $DestinationPath"
} finally {
    if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Recurse -Force -ErrorAction SilentlyContinue }
}