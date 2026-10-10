param([Parameter(Mandatory=$true)][string]$LocalMonoRoot,
 [ValidateSet('x86','x64')][string]$Architecture='x64')
$ErrorActionPreference='Stop'
$repository=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$runtime=(Resolve-Path -LiteralPath $LocalMonoRoot).Path
$library=Join-Path $runtime 'lib/mono-2.0-sgen.lib'
if(!(Test-Path -LiteralPath $library)){throw 'Explicit local Mono import library missing; no download or install occurs'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
if(!$installation){throw 'MSVC is missing'}
$developer=Join-Path $installation 'Common7/Tools/VsDevCmd.bat'
$run=Join-Path $repository ('build/runs/owned-mono-source-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $run -ErrorAction Stop)
$module=Join-Path $repository 'src/ct2trainer/native/mono'
$include=Join-Path $repository 'dependencies/native/mono-api-source/upstream'
$source=$PSScriptRoot
$csc=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if(!(Test-Path -LiteralPath $csc)){throw 'Installed C# compiler is required; it compiles own IL only'}
$managed=Join-Path $run 'OwnedManagedFixture.dll'
$managedLog=(& $csc /nologo /target:library /optimize+ ('/out:'+$managed) (Join-Path $source 'OwnedManagedFixture.cs') 2>&1|Out-String)
[IO.File]::WriteAllText((Join-Path $run 'csharp.log'),$managedLog)
if($LASTEXITCODE-ne0){throw "Own IL build failed; retained $run"}
$commands=@('@echo off',('call "'+$developer+'" -no_logo -arch='+$Architecture+' -host_arch=x64'),'if errorlevel 1 exit /b %errorlevel%',
 ('cl.exe /nologo /W4 /WX /O2 /MD /TC /I"'+$module+'" /I"'+$include+'" /I"'+$source+'" "'+(Join-Path $module 'mono_api.c')+'" "'+(Join-Path $module 'mono_collector.c')+'" "'+(Join-Path $source 'owned_fixture_bootstrap.c')+'" "'+(Join-Path $source 'mono_fixture_host.c')+'" /Fe:OwnedMonoSourceFixture.exe /link "'+$library+'" /INCREMENTAL:NO'),
 'exit /b %errorlevel%')
$batch=Join-Path $run 'build.cmd';[IO.File]::WriteAllLines($batch,$commands,[Text.UTF8Encoding]::new($false))
Push-Location $run
try{$ErrorActionPreference='Continue';$text=(& cmd.exe /d /c $batch 2>&1|Out-String);$code=$LASTEXITCODE;$ErrorActionPreference='Stop'}finally{Pop-Location}
[IO.File]::WriteAllText((Join-Path $run 'compiler.log'),$text)
if($code-ne0){throw "Own fixture build failed; retained $run"}
# No Mono DLL, MSI, class library, config or import library is copied. This is
# compile-only: launching is a separately authorized owned-process gate.
$executable=Join-Path $run 'OwnedMonoSourceFixture.exe'
$inputs=@($library,$csc,(Join-Path $module 'mono_api.c'),(Join-Path $module 'mono_collector.c'),(Join-Path $source 'owned_fixture_bootstrap.c'),(Join-Path $source 'mono_fixture_host.c'),(Join-Path $source 'OwnedManagedFixture.cs'))
$inputPins=@($inputs|ForEach-Object{@{path=$_;sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant();bytes=(Get-Item -LiteralPath $_).Length}})
$report=@{schema='ct2trainer-owned-mono-explicit-local-build/v1';architecture=$Architecture;local_runtime=$runtime;local_import_library=$library;input_pins=$inputPins;runtime_distributed=$false;runtime_executed=$false;child_started=$false;executable=$executable;executable_sha256=(Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant();assembly=$managed;assembly_sha256=(Get-FileHash -LiteralPath $managed -Algorithm SHA256).Hash.ToLowerInvariant();exit_code=$code}
[IO.File]::WriteAllText((Join-Path $run 'build.json'),($report|ConvertTo-Json -Depth 5))
Write-Output $run
