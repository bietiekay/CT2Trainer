#requires -Version 5.1
<#
.SYNOPSIS
Builds the owned x64 target and checks its unmodified baseline on Windows.
.DESCRIPTION
This script never starts Cheat Engine or a trainer. A passing result proves only
that this FixtureTarget.exe prints the expected initial values and increments
ticks by itself. Keep the resulting evidence beside, but separate from, W0-W3.
.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\windows\fixture_target\Invoke-FixturePreflight.ps1
.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\windows\fixture_target\Invoke-FixturePreflight.ps1 -Compiler MinGW
#>
[CmdletBinding()]
param(
    [ValidateSet('Auto', 'MSVC', 'MinGW')]
    [string]$Compiler = 'Auto',
    [string]$OutputDirectory = '',
    [ValidateRange(3, 30)]
    [int]$ObserveSeconds = 4
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Hash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Invoke-Native([string]$Executable, [string[]]$Arguments) {
    # Windows PowerShell 5.1 surfaces redirected native stderr as error records.
    # Preserve it as build evidence and use the actual native exit code.
    $ErrorActionPreference = 'Continue'
    $lines = & $Executable @Arguments 2>&1
    $nativeExitCode = $LASTEXITCODE
    return [pscustomobject]@{
        Text = ($lines | Out-String)
        ExitCode = $nativeExitCode
    }
}

function Get-PeMachine([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 64 -or $bytes[0] -ne 0x4d -or $bytes[1] -ne 0x5a) {
        throw 'Fixture binary has no DOS/PE header.'
    }
    $offset = [BitConverter]::ToInt32($bytes, 0x3c)
    if ($offset -lt 64 -or $offset -gt ($bytes.Length - 6) -or
        $bytes[$offset] -ne 0x50 -or $bytes[$offset + 1] -ne 0x45 -or
        $bytes[$offset + 2] -ne 0 -or $bytes[$offset + 3] -ne 0) {
        throw 'Fixture binary has an invalid PE signature or header offset.'
    }
    return [BitConverter]::ToUInt16($bytes, $offset + 4)
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'The Windows fixture gate requires a 64-bit operating system.'
}
$fixtureDirectory = Split-Path -Parent $PSCommandPath
$repoDirectory = [IO.Path]::GetFullPath((Join-Path $fixtureDirectory '..\..\..'))
$source = Join-Path $fixtureDirectory 'fixture_target.c'
$table = Join-Path $fixtureDirectory 'fixture.ct'
if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or
    -not (Test-Path -LiteralPath $table -PathType Leaf)) {
    throw 'Fixture source or CT is missing.'
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repoDirectory 'build\windows-fixture'
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
[void](New-Item -ItemType Directory -Path $OutputDirectory -Force)
$runId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$evidenceDirectory = Join-Path $OutputDirectory ('preflight-' + $runId)
[void](New-Item -ItemType Directory -Path $evidenceDirectory)
$exe = Join-Path $evidenceDirectory 'FixtureTarget.exe'
$buildLog = Join-Path $evidenceDirectory 'compiler.log'
$versionLog = Join-Path $evidenceDirectory 'compiler-version.log'
$stdoutLog = Join-Path $evidenceDirectory 'target.stdout.log'
$stderrLog = Join-Path $evidenceDirectory 'target.stderr.log'
$manifest = Join-Path $evidenceDirectory 'preflight.json'
$sourceHashBefore = Get-Hash $source
$tableHashBefore = Get-Hash $table

$msvc = Get-Command cl.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$mingw = Get-Command x86_64-w64-mingw32-gcc.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $mingw) {
    $mingw = Get-Command gcc.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
}
switch ($Compiler) {
    'MSVC' { if (-not $msvc) { throw 'cl.exe not found; use an x64 Native Tools prompt.' }; $selected = $msvc; $kind = 'MSVC' }
    'MinGW' { if (-not $mingw) { throw 'MinGW-w64 gcc.exe not found.' }; $selected = $mingw; $kind = 'MinGW' }
    default {
        if ($msvc) { $selected = $msvc; $kind = 'MSVC' }
        elseif ($mingw) { $selected = $mingw; $kind = 'MinGW' }
        else { throw 'No cl.exe or MinGW-w64 gcc.exe found.' }
    }
}
if ($kind -eq 'MSVC') {
    $object = Join-Path $evidenceDirectory 'fixture_target.obj'
    $importLibrary = Join-Path $evidenceDirectory 'FixtureTarget.lib'
    $compilerArguments = @('/W4', '/O2', '/TC', ('/Fe:' + $exe),
        ('/Fo:' + $object), $source, '/link', ('/IMPLIB:' + $importLibrary))
    $versionArguments = @()
} else {
    $compilerArguments = @('-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-o', $exe, $source)
    $versionArguments = @('--version')
}
$versionResult = Invoke-Native $selected.Source $versionArguments
[IO.File]::WriteAllText($versionLog, $versionResult.Text,
    ([System.Text.UTF8Encoding]::new($false)))
$versionLines = @($versionResult.Text -split '\r?\n' | Where-Object { $_.Trim() })
$versionFirstLine = if ($versionLines.Count -gt 0) { $versionLines[0].Trim() } else { $null }
$result = Invoke-Native $selected.Source $compilerArguments
[IO.File]::WriteAllText($buildLog, $result.Text, ([System.Text.UTF8Encoding]::new($false)))
if ($result.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Fixture compilation failed (exit $($result.ExitCode)); inspect $buildLog"
}
if ((Get-Hash $source) -ne $sourceHashBefore -or (Get-Hash $table) -ne $tableHashBefore) {
    throw 'Fixture source or CT changed during the preflight. Discard this run.'
}
$machine = Get-PeMachine $exe
if ($machine -ne 0x8664) {
    throw ('Fixture PE machine is 0x{0:x4}, expected x64 0x8664.' -f $machine)
}
$binaryText = [Text.Encoding]::GetEncoding(28591).GetString([IO.File]::ReadAllBytes($exe))
$markerCount = [regex]::Matches($binaryText, 'CT2T-FIX-2026-01').Count
if ($markerCount -ne 1) {
    throw "Fixture binary has $markerCount static marker occurrences, expected one."
}

$target = $null
try {
    $target = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    Start-Sleep -Seconds $ObserveSeconds
    $target.Refresh()
    if ($target.HasExited) {
        throw "Fixture exited before observation ended (exit $($target.ExitCode))."
    }
} finally {
    if ($null -ne $target) {
        $target.Refresh()
        if (-not $target.HasExited) {
            Stop-Process -Id $target.Id -Force
            [void]$target.WaitForExit(5000)
        }
    }
}

$rows = @()
foreach ($line in (Get-Content -LiteralPath $stdoutLog)) {
    if ($line -match '^PID=(\d+) value=(\d+) pause=(\d+) ticks=(\d+)$') {
        $rows += [pscustomobject]@{
            Pid = [uint64]$Matches[1]
            Value = [uint64]$Matches[2]
            Pause = [uint64]$Matches[3]
            Ticks = [uint64]$Matches[4]
        }
    } elseif ($line -match '^PID=') {
        throw "Malformed fixture state line in $stdoutLog"
    }
}
if ($rows.Count -lt 3) {
    throw "Expected at least three target state lines; inspect $stdoutLog"
}
for ($i = 0; $i -lt $rows.Count; $i++) {
    if ($rows[$i].Pid -ne [uint64]$target.Id -or $rows[$i].Value -ne 1234 -or
        $rows[$i].Pause -ne 0 -or $rows[$i].Ticks -ne [uint64]$i) {
        throw "Unexpected baseline at state line $i; inspect $stdoutLog"
    }
}
$gitHead = $null
$gitStatus = $null
if (Get-Command git.exe -CommandType Application -ErrorAction SilentlyContinue) {
    $gitHeadResult = Invoke-Native 'git.exe' @('-C', $repoDirectory, 'rev-parse', 'HEAD')
    $gitStatusResult = Invoke-Native 'git.exe' @('-C', $repoDirectory, 'status', '--short')
    if ($gitHeadResult.ExitCode -eq 0) { $gitHead = $gitHeadResult.Text.Trim() }
    if ($gitStatusResult.ExitCode -eq 0) { $gitStatus = $gitStatusResult.Text.Trim() }
}
$record = [ordered]@{
    schema = 'ct2trainer-fixture-preflight/v1'
    status = 'target-baseline-passed-ce-and-trainer-unverified'
    run_id = $runId
    captured_utc = (Get-Date).ToUniversalTime().ToString('o')
    windows_version = [Environment]::OSVersion.VersionString
    windows_x64 = [Environment]::Is64BitOperatingSystem
    powershell_version = $PSVersionTable.PSVersion.ToString()
    repo_head = $gitHead
    repo_status_short = $gitStatus
    compiler_kind = $kind
    compiler_path = $selected.Source
    compiler_arguments = $compilerArguments
    compiler_version_first_line = $versionFirstLine
    compiler_version_log_sha256 = Get-Hash $versionLog
    compiler_version_probe_exit_code = $versionResult.ExitCode
    compiler_exit_code = $result.ExitCode
    compiler_log_sha256 = Get-Hash $buildLog
    source_path = $source
    source_sha256 = $sourceHashBefore
    table_path = $table
    table_sha256 = $tableHashBefore
    fixture_exe_path = $exe
    fixture_exe_sha256 = Get-Hash $exe
    fixture_exe_bytes = (Get-Item -LiteralPath $exe).Length
    fixture_pe_machine = ('0x{0:x4}' -f $machine)
    binary_marker_occurrences = $markerCount
    observed_pid = $target.Id
    observed_seconds = $ObserveSeconds
    state_line_count = $rows.Count
    first_state = $rows[0]
    last_state = $rows[$rows.Count - 1]
    stdout_sha256 = Get-Hash $stdoutLog
    stderr_sha256 = Get-Hash $stderrLog
}
[IO.File]::WriteAllText($manifest, ($record | ConvertTo-Json -Depth 8),
    ([System.Text.UTF8Encoding]::new($false)))
Write-Host "Fixture baseline passed. Evidence: $evidenceDirectory"
Write-Host 'CE attach, trainer functionality and standalone EXE remain unverified.'
