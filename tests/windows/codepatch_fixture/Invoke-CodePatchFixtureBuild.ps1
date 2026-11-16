#requires -Version 5.1
# Builds the owned NativeCodePatchFixture.exe targets (x64 and x86) with MSVC.
# Verifies the deterministic byte layout contract:
#   - the 16-byte module marker "CT2T-CPP-2026-01" occurs exactly once,
#   - the 8-byte data block A baseline "DATA_A01" (44 41 54 41 5F 41 30 31)
#     occurs exactly once,
#   - the 4-byte data block B baseline "DATB" (44 41 54 42) occurs exactly
#     once, and
#   - the probe prologue occurs exactly once: B8 5D 5C 5B 5A C3 (x64) and
#     55 8B EC B8 5D 5C 5B 5A 5D C3 (x86, MSVC frame setup with /Od).
# Writes build.json evidence with byte-pinned SHA-256 per architecture.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$OutputDirectory,
    [ValidateSet('x64','x86')][string[]]$Architectures = @('x64','x86'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$utf8 = [Text.UTF8Encoding]::new($false)
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Code-patch evidence directory must be fresh.' }
[void](New-Item -ItemType Directory -Path $OutputDirectory)
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (-not $installation) { throw 'Installed MSVC x86/x64 tools are missing.' }
$developer = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
$sourceDirectory = Join-Path $OutputDirectory 'source'
[void](New-Item -ItemType Directory -Path $sourceDirectory)
$sources = @()
foreach ($inputPath in @((Join-Path $PSScriptRoot 'codepatch_target.c'), $PSCommandPath)) {
    $hash = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $copyPath = Join-Path $sourceDirectory ([IO.Path]::GetFileName($inputPath))
    Copy-Item -LiteralPath $inputPath -Destination $copyPath
    if ((Get-FileHash -LiteralPath $copyPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) { throw 'Source snapshot hash mismatch.' }
    $sources += [pscustomobject]@{path=$inputPath; snapshot=$copyPath; sha256=$hash}
}
$markerPattern = [byte[]]@(0x43,0x54,0x32,0x54,0x2D,0x43,0x50,0x50,0x2D,0x32,0x30,0x32,0x36,0x2D,0x30,0x31)
$dataAPattern = [byte[]]@(0x44,0x41,0x54,0x41,0x5F,0x41,0x30,0x31)
$dataBPattern = [byte[]]@(0x44,0x41,0x54,0x42)
$probePatterns = @{ 'x64' = [byte[]]@(0xB8,0x5D,0x5C,0x5B,0x5A,0xC3);
    'x86' = [byte[]]@(0x55,0x8B,0xEC,0xB8,0x5D,0x5C,0x5B,0x5A,0x5D,0xC3) }
function Count-Occurrences([byte[]]$haystack, [byte[]]$needle) {
    $count = 0
    for ($i = 0; $i -le $haystack.Length - $needle.Length; $i++) {
        $match = $true
        for ($j = 0; $j -lt $needle.Length; $j++) {
            if ($haystack[$i + $j] -ne $needle[$j]) { $match = $false; break }
        }
        if ($match) { $count++ }
    }
    return $count
}
$results = @()
foreach ($architecture in $Architectures) {
    $architectureDirectory = Join-Path $OutputDirectory $architecture
    [void](New-Item -ItemType Directory -Path $architectureDirectory)
    $batch = Join-Path $architectureDirectory 'build.cmd'
    $exe = Join-Path $architectureDirectory 'NativeCodePatchFixture.exe'
    $commands = @('@echo off', ('call "' + $developer + '" -no_logo -arch=' + $architecture + ' -host_arch=x64'),
        'if errorlevel 1 exit /b %errorlevel%', 'where cl.exe > compiler-path.log', 'cl.exe > compiler-version.log 2>&1',
        ('cl.exe /nologo /W4 /WX /Od /TC "' + (Join-Path $sourceDirectory 'codepatch_target.c') + '" /Fe:NativeCodePatchFixture.exe /link /INCREMENTAL:NO'),
        'exit /b %errorlevel%')
    [IO.File]::WriteAllLines($batch, $commands, $utf8)
    Push-Location $architectureDirectory
    try {
        $ErrorActionPreference = 'Continue'
        $compilerText = (& cmd.exe /d /c $batch 2>&1 | Out-String)
        $compilerExit = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
    } finally { Pop-Location }
    [IO.File]::WriteAllText((Join-Path $architectureDirectory 'compiler.log'), $compilerText, $utf8)
    if ($compilerExit -ne 0 -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Code-patch $architecture build failed; preserved $architectureDirectory" }
    $bytes = [IO.File]::ReadAllBytes($exe)
    $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
    $machine = [BitConverter]::ToUInt16($bytes, $peOffset + 4)
    $expectedMachine = if ($architecture -eq 'x64') {0x8664} else {0x14c}
    if ($machine -ne $expectedMachine) { throw 'Code-patch fixture PE architecture mismatch.' }
    $markerCount = Count-Occurrences $bytes $markerPattern
    $dataACount = Count-Occurrences $bytes $dataAPattern
    $dataBCount = Count-Occurrences $bytes $dataBPattern
    $probePattern = $probePatterns[$architecture]
    $probeCount = Count-Occurrences $bytes $probePattern
    if ($markerCount -ne 1) { throw "Code-patch fixture marker pattern count is $markerCount (expected exactly 1) for $architecture." }
    if ($dataACount -ne 1) { throw "Code-patch fixture data block A baseline count is $dataACount (expected exactly 1) for $architecture." }
    if ($dataBCount -ne 1) { throw "Code-patch fixture data block B baseline count is $dataBCount (expected exactly 1) for $architecture." }
    if ($probeCount -ne 1) { throw "Code-patch fixture probe prologue count is $probeCount (expected exactly 1) for $architecture." }
    $results += [pscustomobject]@{architecture=$architecture; pe_machine=$machine; executable=$exe;
        bytes=$bytes.Length; sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant();
        marker_occurrences=$markerCount; data_a_baseline_occurrences=$dataACount;
        data_b_baseline_occurrences=$dataBCount; probe_prologue_occurrences=$probeCount;
        compiler_log=(Join-Path $architectureDirectory 'compiler.log'); compiler_exit_code=$compilerExit;
        compiler_command=$batch; compiler_version=(Join-Path $architectureDirectory 'compiler-version.log');
        compiler_path=(Join-Path $architectureDirectory 'compiler-path.log')}
    Write-Output ("{0}: sha256={1} bytes={2} marker=1 data_a=1 data_b=1 probe=1" -f $architecture, $results[-1].sha256, $bytes.Length)
}
foreach ($source in $sources) {
    if ((Get-FileHash -LiteralPath $source.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $source.sha256) { throw 'Code-patch source changed during build.' }
}
$report = [pscustomobject]@{schema='ct2trainer-owned-codepatch-build/v1'; status='passed'; ce_inputs=@();
    sources=$sources; results=$results; msvc_installation=$installation; runtime_verified=$false}
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'build.json'), ($report | ConvertTo-Json -Depth 8), $utf8)
Write-Output $OutputDirectory
