[CmdletBinding()]
param(
    [ValidateSet("P0", "Packaging")]
    [string]$Phase = "P0"
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$RequiredNode = "v24.12.0"
$RequiredNpm = "11.6.2"
$RequiredPython = "3.11.5"
$Failures = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]
$Ready = New-Object System.Collections.Generic.List[string]
$Missing = New-Object System.Collections.Generic.List[string]
$SigningOnly = New-Object System.Collections.Generic.List[string]

function Add-Ready([string]$Message) { $Ready.Add($Message) | Out-Null }
function Add-Failure([string]$Message) { $Failures.Add($Message) | Out-Null; $Missing.Add($Message) | Out-Null }
function Add-Warning([string]$Message) { $Warnings.Add($Message) | Out-Null }

function Get-CommandPath([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { return $null }
    return $cmd.Source
}

function Get-ToolOutput([string]$Command, [string[]]$Arguments) {
    try {
        $output = & $Command @Arguments 2>$null
        if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { return $null }
        return ($output | Select-Object -First 1)
    } catch {
        return $null
    }
}

function Find-CPython311 {
    $candidates = New-Object System.Collections.Generic.List[string]
    try {
        $pyOutput = & py -0p 2>$null
        foreach ($line in $pyOutput) {
            if ($line -match "(?<path>[A-Za-z]:\\.*python\.exe)") {
                $candidates.Add($Matches.path) | Out-Null
            }
        }
    } catch {}
    try {
        $whereOutput = & where.exe python 2>$null
        foreach ($line in $whereOutput) {
            if ($line -match "^[A-Za-z]:\\.*python(\.exe)?$") {
                $candidates.Add($line) | Out-Null
            }
        }
    } catch {}

    foreach ($candidate in $candidates | Select-Object -Unique) {
        $probe = Get-ToolOutput $candidate @("-c", "import platform,sys; print(platform.python_implementation() + '|' + platform.python_version() + '|' + sys.executable + '|' + sys.prefix)")
        if ($null -eq $probe) { continue }
        $parts = $probe -split "\|"
        if ($parts.Count -ge 4 -and $parts[0] -eq "CPython" -and $parts[1] -eq $RequiredPython -and $parts[3] -notmatch "(?i)conda|anaconda") {
            return $candidate
        }
    }
    return $null
}

function Test-ExactPackageJsonPins {
    $packagePath = Join-Path $Root "frontend\package.json"
    if (-not (Test-Path -LiteralPath $packagePath)) {
        Add-Failure "frontend/package.json is missing"
        return
    }
    $package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
    $bad = New-Object System.Collections.Generic.List[string]
    foreach ($section in @("dependencies", "devDependencies")) {
        if (-not $package.PSObject.Properties.Name.Contains($section)) { continue }
        foreach ($prop in $package.$section.PSObject.Properties) {
            $value = [string]$prop.Value
            if ($value -eq "latest" -or $value -eq "*" -or $value.StartsWith("^") -or $value.StartsWith("~")) {
                $bad.Add("$section/$($prop.Name)=$value") | Out-Null
            }
        }
    }
    if ($bad.Count -gt 0) {
        Add-Failure "package.json has non-exact dependency declarations: $($bad -join ', ')"
    } else {
        Add-Ready "package.json direct dependencies are exact"
    }
}

function Test-FileExists([string]$RelativePath, [string]$Label) {
    if (Test-Path -LiteralPath (Join-Path $Root $RelativePath)) {
        Add-Ready "$Label exists"
    } else {
        Add-Failure "$Label is missing"
    }
}

function Test-OptionalTool([string]$Command, [string]$Label) {
    $path = Get-CommandPath $Command
    if ($null -eq $path) {
        $Missing.Add($Label) | Out-Null
        return $false
    }
    Add-Ready "${Label}: $path"
    return $true
}

Push-Location $Root
try {
    $nodeVersion = Get-ToolOutput "node" @("--version")
    if ($nodeVersion -eq $RequiredNode) { Add-Ready "Node $nodeVersion" } else { Add-Failure "Node must be $RequiredNode, found $nodeVersion" }

    $npmVersion = Get-ToolOutput "npm" @("--version")
    if ($npmVersion -eq $RequiredNpm) { Add-Ready "npm $npmVersion" } else { Add-Failure "npm must be $RequiredNpm, found $npmVersion" }

    $cpython = Find-CPython311
    if ($null -eq $cpython) { Add-Failure "independent CPython $RequiredPython was not found" } else { Add-Ready "independent CPython ${RequiredPython}: $cpython" }

    $defaultPython = Get-CommandPath "python"
    if ($null -eq $defaultPython) {
        Add-Warning "default python is not on PATH"
    } elseif ($defaultPython -match "(?i)conda|anaconda") {
        Add-Warning "default python appears to be Conda: $defaultPython"
    } else {
        Add-Ready "default python is not Conda: $defaultPython"
    }

    Test-ExactPackageJsonPins
    Test-FileExists "frontend\package-lock.json" "frontend/package-lock.json"
    Test-FileExists "frontend\.npmrc" "frontend/.npmrc"
    foreach ($req in @("runtime.in", "runtime.lock", "dev.in", "dev.lock", "desktop.in", "desktop.lock")) {
        Test-FileExists "requirements\$req" "requirements/$req"
    }
    Test-FileExists "version.json" "version.json"

    $gitPath = Get-CommandPath "git"
    if ($null -eq $gitPath) { Add-Failure "git is missing" } else { Add-Ready "git: $gitPath" }

    if ($null -ne $cpython) {
        & $cpython scripts\sync_version.py --check | Out-Host
        if ($LASTEXITCODE -eq 0) { Add-Ready "sync_version.py --check" } else { Add-Failure "sync_version.py --check failed" }
    }

    if ($Phase -eq "Packaging") {
        Test-OptionalTool "rustc" "rustc" | Out-Null
        Test-OptionalTool "cargo" "cargo" | Out-Null
        Test-OptionalTool "rustup" "rustup" | Out-Null

        $rustup = Get-CommandPath "rustup"
        if ($null -eq $rustup) {
            $Missing.Add("stable-msvc Rust toolchain") | Out-Null
        } else {
            $toolchains = & rustup toolchain list 2>$null
            if ($toolchains -match "stable.*msvc") { Add-Ready "stable-msvc Rust toolchain" } else { $Missing.Add("stable-msvc Rust toolchain") | Out-Null }
        }

        Test-OptionalTool "cl" "MSVC cl" | Out-Null
        Test-OptionalTool "link" "MSVC link" | Out-Null

        $sdkRoots = @(
            "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
            "${env:ProgramFiles}\Windows Kits\10\bin"
        )
        if ($sdkRoots | Where-Object { $_ -and (Test-Path -LiteralPath $_) }) { Add-Ready "Windows SDK directory" } else { $Missing.Add("Windows SDK") | Out-Null }

        $webViewRoots = @(
            "${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application",
            "${env:ProgramFiles}\Microsoft\EdgeWebView\Application"
        )
        if ($webViewRoots | Where-Object { $_ -and (Test-Path -LiteralPath $_) }) { Add-Ready "WebView2 Runtime" } else { $Missing.Add("WebView2 Runtime") | Out-Null }

        Test-OptionalTool "makensis" "NSIS makensis" | Out-Null
        if (-not (Test-OptionalTool "signtool" "signtool")) { $SigningOnly.Add("signtool") | Out-Null }

        if (Test-Path -LiteralPath (Join-Path $Root "src-tauri\Cargo.lock")) { Add-Ready "future src-tauri/Cargo.lock" } else { $Missing.Add("future src-tauri/Cargo.lock") | Out-Null }
        if (Test-Path -LiteralPath (Join-Path $Root "src-tauri\tauri.conf.json")) { Add-Ready "future Tauri config" } else { $Missing.Add("future Tauri config") | Out-Null }
    }
} finally {
    Pop-Location
}

Write-Host "Ready:"
foreach ($item in $Ready | Select-Object -Unique) { Write-Host "  OK $item" }

if ($Warnings.Count -gt 0) {
    Write-Host "Warnings:"
    foreach ($item in $Warnings | Select-Object -Unique) { Write-Host "  WARN $item" }
}

if ($Missing.Count -gt 0) {
    Write-Host "Missing:"
    foreach ($item in $Missing | Select-Object -Unique) { Write-Host "  MISSING $item" }
}

if ($SigningOnly.Count -gt 0) {
    Write-Host "Signing-only:"
    foreach ($item in $SigningOnly | Select-Object -Unique) { Write-Host "  SIGNING $item" }
}

if ($Phase -eq "P0" -and $Failures.Count -gt 0) { exit 1 }
if ($Phase -eq "Packaging" -and $Missing.Count -gt 0) { exit 1 }
exit 0