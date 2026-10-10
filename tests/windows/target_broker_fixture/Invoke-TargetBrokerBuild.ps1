#requires -Version 5.1
[CmdletBinding()]
param([string]$OutputDirectory = '', [ValidateSet('x64','x86')][string[]]$Architectures = @('x64','x86'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$utf8 = [Text.UTF8Encoding]::new($false)
if (-not $OutputDirectory) {
    $runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    $OutputDirectory = Join-Path $repoDirectory ('build\runs\native-target-broker-' + $runId)
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Broker evidence directory must be fresh.' }
[void](New-Item -ItemType Directory -Path $OutputDirectory)
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (-not $installation) { throw 'Installed MSVC x86/x64 tools are missing.' }
$developer = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
$sourceDirectory = Join-Path $OutputDirectory 'source'
[void](New-Item -ItemType Directory -Path $sourceDirectory)
$sources = @()
foreach ($inputPath in @((Join-Path $repoDirectory 'src\ct2trainer\native\target_broker\broker.c'),
    (Join-Path $repoDirectory 'src\ct2trainer\native\target_broker\broker_abi.h'), (Join-Path $PSScriptRoot 'broker_target.c'), $PSCommandPath)) {
    $hash = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $copyPath = Join-Path $sourceDirectory ([IO.Path]::GetFileName($inputPath))
    Copy-Item -LiteralPath $inputPath -Destination $copyPath
    if ((Get-FileHash -LiteralPath $copyPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) { throw 'Broker source snapshot hash mismatch.' }
    $sources += [pscustomobject]@{path=$inputPath; snapshot=$copyPath; sha256=$hash}
}
[IO.File]::WriteAllText((Join-Path $sourceDirectory 'broker.def'), "LIBRARY CT2TrainerOwnedBroker`r`nEXPORTS`r`nTFBrokerStart`r`nTFBrokerPumpMain`r`nTFBrokerInspect`r`n", $utf8)
$results = @()
foreach ($architecture in $Architectures) {
    $architectureDirectory = Join-Path $OutputDirectory $architecture
    [void](New-Item -ItemType Directory -Path $architectureDirectory)
    $batch = Join-Path $architectureDirectory 'build.cmd'
    $exe = Join-Path $architectureDirectory 'NativeTargetBrokerFixture.exe'
    $dll = Join-Path $architectureDirectory 'CT2TrainerOwnedBroker.dll'
    $commands = @('@echo off', ('call "' + $developer + '" -no_logo -arch=' + $architecture + ' -host_arch=x64'),
        'if errorlevel 1 exit /b %errorlevel%', 'where cl.exe > compiler-path.log', 'cl.exe > compiler-version.log 2>&1',
        ('cl.exe /nologo /W4 /WX /O2 /TC /LD /I"' + $sourceDirectory + '" "' + (Join-Path $sourceDirectory 'broker.c') + '" /Fe:CT2TrainerOwnedBroker.dll /link advapi32.lib /DEF:"' + (Join-Path $sourceDirectory 'broker.def') + '" /INCREMENTAL:NO'),
        'if errorlevel 1 exit /b %errorlevel%',
        ('cl.exe /nologo /W4 /WX /O2 /TC /I"' + $sourceDirectory + '" "' + (Join-Path $sourceDirectory 'broker_target.c') + '" /Fe:NativeTargetBrokerFixture.exe /link /INCREMENTAL:NO'),
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
    if ($compilerExit -ne 0 -or -not (Test-Path -LiteralPath $exe -PathType Leaf) -or -not (Test-Path -LiteralPath $dll -PathType Leaf)) { throw "Broker $architecture build failed; preserved $architectureDirectory" }
    $components = @()
    foreach ($binary in @($exe, $dll)) {
        $bytes = [IO.File]::ReadAllBytes($binary)
        $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
        $machine = [BitConverter]::ToUInt16($bytes, $peOffset + 4)
        $expectedMachine = if ($architecture -eq 'x64') {0x8664} else {0x14c}
        if ($machine -ne $expectedMachine) { throw 'Broker fixture PE architecture mismatch.' }
        $components += [pscustomobject]@{path=$binary; pe_machine=$machine; sha256=(Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $results += [pscustomobject]@{architecture=$architecture; executable=$exe; dll=$dll; components=$components;
        compiler_log=(Join-Path $architectureDirectory 'compiler.log'); compiler_exit_code=$compilerExit}
}
$report = [pscustomobject]@{schema='ct2trainer-owned-target-broker-build/v1'; status='passed'; ce_inputs=@();
    sources=$sources; results=$results; runtime_verified=$false; msvc_installation=$installation}
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'verification.json'), ($report | ConvertTo-Json -Depth 8), $utf8)
Write-Output $OutputDirectory
