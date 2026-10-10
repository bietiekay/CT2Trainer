#requires -Version 5.1
[CmdletBinding()]
param([string]$OutputDirectory = '', [ValidateSet('x64','x86')][string[]]$Architectures = @('x64','x86'),
      [string]$RepositoryDirectory = '', [string]$SourceDirectory = '', [switch]$TestPlatformFault)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $RepositoryDirectory) { $RepositoryDirectory = Join-Path $PSScriptRoot '..\..\..' }
$repoDirectory = [IO.Path]::GetFullPath($RepositoryDirectory)
$utf8 = [Text.UTF8Encoding]::new($false)
if (-not $OutputDirectory) {
    $runId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    $OutputDirectory = Join-Path $repoDirectory ('build\runs\native-clock-adapter-' + $runId)
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Adapter evidence directory must be fresh.' }
[void](New-Item -ItemType Directory -Path $OutputDirectory)
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) { throw 'Installed MSVC discovery tool is missing.' }
$installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (-not $installation) { throw 'Installed MSVC x86/x64 tools are missing.' }
$developer = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
$snapshotDirectory = Join-Path $OutputDirectory 'source'
[void](New-Item -ItemType Directory -Path $snapshotDirectory)
if ($SourceDirectory) {
    $inputSources = @('clock_core.h','clock_core.c','clock_adapter.h','clock_adapter.c','adapter_fixture.c') | ForEach-Object { Join-Path $SourceDirectory $_ }
} else {
    $inputSources = @('clock_core.h','clock_core.c','clock_adapter.h','clock_adapter.c') | ForEach-Object { Join-Path $repoDirectory ('src\ct2trainer\native\clock\'+$_) }
    $inputSources += Join-Path $PSScriptRoot 'adapter_fixture.c'
}
$inputSources += $PSCommandPath
$sources = @()
foreach ($inputPath in $inputSources) {
    $hash = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $copyPath = Join-Path $snapshotDirectory ([IO.Path]::GetFileName($inputPath))
    Copy-Item -LiteralPath $inputPath -Destination $copyPath
    if ((Get-FileHash -LiteralPath $copyPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) { throw 'Adapter source snapshot mismatch.' }
    $sources += [pscustomobject]@{path=$inputPath; snapshot=$copyPath; sha256=$hash}
}
$results = @()
$testingDefine = if ($TestPlatformFault) {'/DTF_CLOCK_ADAPTER_TESTING=1 '} else {''}
$testModes = @('fake','calibration','real','deadline','cancel','cancel_busy','fence_concurrency')
if ($TestPlatformFault) { $testModes += 'platform' }
foreach ($architecture in $Architectures) {
    $architectureDirectory = Join-Path $OutputDirectory $architecture
    [void](New-Item -ItemType Directory -Path $architectureDirectory)
    $batch = Join-Path $architectureDirectory 'build.cmd'
    $exe = Join-Path $architectureDirectory 'NativeClockAdapterFixture.exe'
    $dll = Join-Path $architectureDirectory 'NativeClockAdapter.dll'
    $commands = @(
        '@echo off',
        ('call "' + $developer + '" -no_logo -arch=' + $architecture + ' -host_arch=x64'),
        'if errorlevel 1 exit /b %errorlevel%',
        'where cl.exe > compiler-path.log', 'cl.exe > compiler-version.log 2>&1',
        ('cl.exe /nologo /W4 /WX /O2 /MT /TC /c /I"' + $snapshotDirectory + '" "' + (Join-Path $snapshotDirectory 'clock_core.c') + '" /Fo:clock_core.obj'),
        'if errorlevel 1 exit /b %errorlevel%',
        ('cl.exe /nologo /W4 /WX /O2 /MT /TC ' + $testingDefine + '/c /I"' + $snapshotDirectory + '" "' + (Join-Path $snapshotDirectory 'clock_adapter.c') + '" /Fo:clock_adapter.obj'),
        'if errorlevel 1 exit /b %errorlevel%',
        'link.exe /nologo /DLL clock_core.obj clock_adapter.obj kernel32.lib /out:NativeClockAdapter.dll',
        'if errorlevel 1 exit /b %errorlevel%',
        ('cl.exe /nologo /W4 /WX /O2 /MT /TC /c /I"' + $snapshotDirectory + '" "' + (Join-Path $snapshotDirectory 'adapter_fixture.c') + '" /Fo:adapter_fixture.obj'),
        'if errorlevel 1 exit /b %errorlevel%',
        'link.exe /nologo adapter_fixture.obj kernel32.lib /out:NativeClockAdapterFixture.exe',
        'if errorlevel 1 exit /b %errorlevel%',
        'dumpbin.exe /headers /exports /imports NativeClockAdapter.dll > adapter-pe.log',
        'exit /b %errorlevel%'
    )
    [IO.File]::WriteAllLines($batch, $commands, $utf8)
    Push-Location $architectureDirectory
    try {
        $ErrorActionPreference = 'Continue'
        $compilerText = (& cmd.exe /d /c $batch 2>&1 | Out-String)
        $compilerExit = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
    } finally { Pop-Location }
    [IO.File]::WriteAllText((Join-Path $architectureDirectory 'compiler.log'), $compilerText, $utf8)
    if ($compilerExit -ne 0 -or -not (Test-Path -LiteralPath $exe -PathType Leaf) -or -not (Test-Path -LiteralPath $dll -PathType Leaf)) { throw "Adapter $architecture build failed; preserved $architectureDirectory" }
    $dllHash = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
    $expectedMachine = if ($architecture -eq 'x64') {0x8664} else {0x14c}
    $expectedBits = if ($architecture -eq 'x64') {64} else {32}
    foreach ($binary in @($exe,$dll)) {
        $bytes = [IO.File]::ReadAllBytes($binary)
        $peOffset = [BitConverter]::ToInt32($bytes,0x3c)
        if ([BitConverter]::ToUInt16($bytes,$peOffset+4) -ne $expectedMachine) { throw 'Adapter fixture PE architecture mismatch.' }
    }
    foreach ($mode in $testModes) {
        $stdout = Join-Path $architectureDirectory ($mode+'.stdout.json')
        $stderr = Join-Path $architectureDirectory ($mode+'.stderr.log')
        $fixture = Start-Process -FilePath $exe -ArgumentList @(('"'+$dll+'"'),$mode) -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        [void]$fixture.Handle
        if (-not $fixture.WaitForExit(20000)) { Stop-Process -Id $fixture.Id -Force; throw "Adapter $architecture/$mode timed out" }
        $fixture.Refresh()
        if ($fixture.ExitCode -ne 0) { throw "Adapter $architecture/$mode failed; preserved $architectureDirectory" }
        $observed = Get-Content -LiteralPath $stdout -Raw | ConvertFrom-Json
        if ($observed.schema -ne 'ct2trainer-clock-adapter-fixture/v2' -or $observed.pointer_bits -ne $expectedBits -or $observed.mode -ne $mode -or
            -not $observed.retained_after_free -or $observed.checks -lt 15) { throw 'Adapter fixture output contract mismatch.' }
        if ((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $dllHash) { throw 'Owned loaded DLL changed during fixture.' }
        $results += [pscustomobject]@{architecture=$architecture; mode=$mode; checks=$observed.checks; executable=$exe; dll=$dll; dll_sha256=$dllHash; stdout=$stdout; stderr=$stderr; exit_code=$fixture.ExitCode}
    }
}
foreach ($source in $sources) { if ((Get-FileHash -LiteralPath $source.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $source.sha256) { throw 'Adapter source changed during evidence run.' } }
$report = [pscustomobject]@{schema='ct2trainer-clock-adapter-verification/v2'; utc=(Get-Date).ToUniversalTime().ToString('o'); status='passed'; sources=$sources; results=$results;
    msvc_installation=$installation; os=[Environment]::OSVersion.VersionString;
    test_only_platform_fault_export=[bool]$TestPlatformFault;
    scope='Only owned local host loading its exact freshly built DLL. No hooks, injection, remote process, game or CE input.'}
$reportPath = Join-Path $OutputDirectory 'verification.json'
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 10), $utf8)
Write-Output $reportPath
