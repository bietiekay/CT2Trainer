#requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$OutputDirectory,
    [ValidateSet('x64','x86')][string[]]$Architectures = @('x64','x86'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$utf8 = [Text.UTF8Encoding]::new($false)
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw 'String evidence directory must be fresh.' }
[void](New-Item -ItemType Directory -Path $OutputDirectory)
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (-not $installation) { throw 'Installed MSVC x86/x64 tools are missing.' }
$developer = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
$sourceDirectory = Join-Path $OutputDirectory 'source'
[void](New-Item -ItemType Directory -Path $sourceDirectory)
$sources = @()
foreach ($inputPath in @((Join-Path $PSScriptRoot 'string_target.c'), $PSCommandPath)) {
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
    $exe = Join-Path $architectureDirectory 'NativeStringFixture.exe'
    $commands = @('@echo off', ('call "' + $developer + '" -no_logo -arch=' + $architecture + ' -host_arch=x64'),
        'if errorlevel 1 exit /b %errorlevel%', 'where cl.exe > compiler-path.log', 'cl.exe > compiler-version.log 2>&1',
        ('cl.exe /nologo /W4 /WX /Od /TC "' + (Join-Path $sourceDirectory 'string_target.c') + '" /Fe:NativeStringFixture.exe /link /INCREMENTAL:NO'),
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
    if ($compilerExit -ne 0 -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "String $architecture build failed; preserved $architectureDirectory" }
    $bytes = [IO.File]::ReadAllBytes($exe)
    $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
    $machine = [BitConverter]::ToUInt16($bytes, $peOffset + 4)
    $expectedMachine = if ($architecture -eq 'x64') {0x8664} else {0x14c}
    if ($machine -ne $expectedMachine) { throw 'String fixture PE architecture mismatch.' }
    $results += [pscustomobject]@{architecture=$architecture; pe_machine=$machine; executable=$exe;
        sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant();
        compiler_log=(Join-Path $architectureDirectory 'compiler.log'); compiler_exit_code=$compilerExit;
        compiler_command=$batch; compiler_version=(Join-Path $architectureDirectory 'compiler-version.log');
        compiler_path=(Join-Path $architectureDirectory 'compiler-path.log')}
}
foreach ($source in $sources) {
    if ((Get-FileHash -LiteralPath $source.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $source.sha256) { throw 'String source changed during build.' }
}
$report = [pscustomobject]@{schema='ct2trainer-owned-string-build/v1'; status='passed'; ce_inputs=@();
    sources=$sources; results=$results; msvc_installation=$installation; runtime_verified=$false}
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'verification.json'), ($report | ConvertTo-Json -Depth 8), $utf8)
Write-Output $OutputDirectory
