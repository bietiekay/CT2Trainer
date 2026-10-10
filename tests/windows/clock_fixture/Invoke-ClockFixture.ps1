#requires -Version 5.1
[CmdletBinding()]
param([string]$OutputDirectory = '', [ValidateSet('x64','x86')][string[]]$Architectures = @('x64','x86'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$utf8 = [Text.UTF8Encoding]::new($false)
if (-not $OutputDirectory) {
    $runId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    $OutputDirectory = Join-Path $repoDirectory ('build\runs\native-clock-' + $runId)
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Clock evidence directory must be fresh.' }
[void](New-Item -ItemType Directory -Path $OutputDirectory)
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) { throw 'Installed MSVC discovery tool is missing.' }
$installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (-not $installation) { throw 'Installed MSVC x86/x64 tools are missing.' }
$developer = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
$sourceDirectory = Join-Path $OutputDirectory 'source'
[void](New-Item -ItemType Directory -Path $sourceDirectory)
$inputs = @(
    (Join-Path $repoDirectory 'src\ct2trainer\native\clock\clock_core.h'),
    (Join-Path $repoDirectory 'src\ct2trainer\native\clock\clock_core.c'),
    (Join-Path $PSScriptRoot 'clock_fixture.c'),
    $PSCommandPath
)
$sources = @()
foreach ($inputPath in $inputs) {
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
    $exe = Join-Path $architectureDirectory 'NativeClockFixture.exe'
    $commands = @(
        '@echo off',
        ('call "' + $developer + '" -no_logo -arch=' + $architecture + ' -host_arch=x64'),
        'if errorlevel 1 exit /b %errorlevel%',
        'where cl.exe > compiler-path.log',
        'cl.exe > compiler-version.log 2>&1',
        ('cl.exe /nologo /W4 /WX /O2 /TC /c /I"' + $sourceDirectory + '" "' + (Join-Path $sourceDirectory 'clock_core.c') + '" /Fo:clock_core.obj'),
        'if errorlevel 1 exit /b %errorlevel%',
        ('cl.exe /nologo /W4 /WX /O2 /TC /c /I"' + $sourceDirectory + '" "' + (Join-Path $sourceDirectory 'clock_fixture.c') + '" /Fo:clock_fixture.obj'),
        'if errorlevel 1 exit /b %errorlevel%',
        'link.exe /nologo clock_core.obj clock_fixture.obj kernel32.lib winmm.lib /out:NativeClockFixture.exe',
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
    if ($compilerExit -ne 0 -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Clock $architecture build failed; preserved $architectureDirectory" }
    $stdout = Join-Path $architectureDirectory 'fixture.stdout.json'
    $stderr = Join-Path $architectureDirectory 'fixture.stderr.log'
    $fixture = Start-Process -FilePath $exe -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    # Pin the process handle before waiting; Windows PowerShell otherwise can
    # lose ExitCode after a short-lived redirected process has already exited.
    [void]$fixture.Handle
    if (-not $fixture.WaitForExit(20000)) {
        Stop-Process -Id $fixture.Id -Force
        throw "Clock $architecture fixture timed out; preserved $architectureDirectory"
    }
    $fixture.Refresh()
    if ($fixture.ExitCode -ne 0) { throw "Clock $architecture fixture failed; preserved $architectureDirectory" }
    $observed = Get-Content -LiteralPath $stdout -Raw | ConvertFrom-Json
    $expectedBits = if ($architecture -eq 'x64') {64} else {32}
    $bytes = [IO.File]::ReadAllBytes($exe)
    $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
    $machine = [BitConverter]::ToUInt16($bytes, $peOffset + 4)
    $expectedMachine = if ($architecture -eq 'x64') {0x8664} else {0x14c}
    if ($observed.schema -ne 'ct2trainer-clock-fixture/v1' -or $observed.pointer_bits -ne $expectedBits -or
        $machine -ne $expectedMachine -or $observed.checks -lt 1100 -or $observed.vectors.Count -ne 256) { throw 'Clock fixture result/PE contract mismatch.' }
    $results += [pscustomobject]@{
        architecture=$architecture; pe_machine=$machine; executable=$exe;
        sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant();
        exit_code=$fixture.ExitCode; checks=$observed.checks; stdout=$stdout; stderr=$stderr;
        compiler_command=$batch; compiler_log=(Join-Path $architectureDirectory 'compiler.log');
        compiler_version=(Join-Path $architectureDirectory 'compiler-version.log');
        compiler_path=(Join-Path $architectureDirectory 'compiler-path.log')
    }
}
foreach ($source in $sources) {
    if ((Get-FileHash -LiteralPath $source.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $source.sha256) { throw 'Clock source changed during evidence run.' }
}
$report = [pscustomobject]@{
    schema='ct2trainer-clock-verification/v1'; utc=(Get-Date).ToUniversalTime().ToString('o');
    status='passed'; sources=$sources; results=$results; msvc_installation=$installation;
    os=[Environment]::OSVersion.VersionString;
    scope='Owned local clock core only: no hooks, DLL loading, remote process or game execution.'
}
$reportPath = Join-Path $OutputDirectory 'verification.json'
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 10), $utf8)
Write-Output $reportPath
