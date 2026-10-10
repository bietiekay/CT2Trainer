#requires -Version 5.1
[CmdletBinding()]
param([string]$OutputDirectory = '', [ValidateSet('x64','x86')][string[]]$Architectures = @('x64','x86'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$utf8 = [Text.UTF8Encoding]::new($false)
if (-not $OutputDirectory) {
    $runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    $OutputDirectory = Join-Path $repoDirectory ('build\runs\native-scan-fixture-' + $runId)
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Scan evidence directory must be fresh.' }
[void](New-Item -ItemType Directory -Path $OutputDirectory)
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (-not $installation) { throw 'Installed MSVC x86/x64 tools are missing.' }
$developer = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
$sourceDirectory = Join-Path $OutputDirectory 'source'
[void](New-Item -ItemType Directory -Path $sourceDirectory)
$sources = @()
foreach ($inputPath in @((Join-Path $PSScriptRoot 'scan_target.c'), $PSCommandPath)) {
    $hash = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $copyPath = Join-Path $sourceDirectory ([IO.Path]::GetFileName($inputPath))
    Copy-Item -LiteralPath $inputPath -Destination $copyPath
    if ((Get-FileHash -LiteralPath $copyPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) { throw 'Source snapshot hash mismatch.' }
    $sources += [pscustomobject]@{path=$inputPath; snapshot=$copyPath; sha256=$hash}
}
$results = @()
foreach ($architecture in $Architectures) {
    $architectureDirectory = Join-Path $OutputDirectory $architecture
    [void](New-Item -ItemType Directory -Path $architectureDirectory)
    $batch = Join-Path $architectureDirectory 'build.cmd'
    $exe = Join-Path $architectureDirectory 'NativeScanFixture.exe'
    # /Od keeps the runtime pattern generator from creating extra pooled constants.
    $commands = @('@echo off', ('call "' + $developer + '" -no_logo -arch=' + $architecture + ' -host_arch=x64'),
        'if errorlevel 1 exit /b %errorlevel%', 'where cl.exe > compiler-path.log', 'cl.exe > compiler-version.log 2>&1',
        ('cl.exe /nologo /W4 /WX /Od /TC "' + (Join-Path $sourceDirectory 'scan_target.c') + '" /Fe:NativeScanFixture.exe /link /INCREMENTAL:NO'),
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
    if ($compilerExit -ne 0 -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Scan $architecture build failed; preserved $architectureDirectory" }
    $bytes = [IO.File]::ReadAllBytes($exe)
    $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
    $machine = [BitConverter]::ToUInt16($bytes, $peOffset + 4)
    $expectedMachine = if ($architecture -eq 'x64') {0x8664} else {0x14c}
    if ($machine -ne $expectedMachine) { throw 'Scan fixture PE architecture mismatch.' }
    $results += [pscustomobject]@{architecture=$architecture; pe_machine=$machine; executable=$exe;
        sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant();
        compiler_log=(Join-Path $architectureDirectory 'compiler.log'); compiler_exit_code=$compilerExit}
}
$report = [pscustomobject]@{schema='ct2trainer-owned-scan-build/v1'; status='passed'; ce_inputs=@();
    sources=$sources; results=$results; runtime_verified=$false}
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'verification.json'), ($report | ConvertTo-Json -Depth 8), $utf8)
Write-Output $OutputDirectory
