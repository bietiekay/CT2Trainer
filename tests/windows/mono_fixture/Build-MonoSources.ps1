param([ValidateSet('x86','x64')][string[]]$Architectures=@('x64','x86'))
$ErrorActionPreference='Stop'
$draftDirectory=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (!$installation) {throw 'MSVC is missing'}
$developer=Join-Path $installation 'Common7/Tools/VsDevCmd.bat'
$run=Join-Path $draftDirectory ('build/runs/mono-source-build-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $run -ErrorAction Stop)
$utf8=[Text.UTF8Encoding]::new($false)
$moduleDirectory=Join-Path $draftDirectory 'src/ct2trainer/native/mono'
$includeDirectory=Join-Path $draftDirectory 'dependencies/native/mono-api-source/upstream'
$records=@()
foreach ($architecture in $Architectures) {
 $output=Join-Path $run $architecture
 [void](New-Item -ItemType Directory -Path $output)
 $commands=@('@echo off',('call "'+$developer+'" -no_logo -arch='+$architecture+' -host_arch=x64'),
  'if errorlevel 1 exit /b %errorlevel%','where cl.exe > compiler-path.log','cl.exe > compiler-version.log 2>&1',
  ('cl.exe /nologo /W4 /WX /O2 /MD /TC /c /I"'+$moduleDirectory+'" /I"'+$includeDirectory+'" "'+(Join-Path $moduleDirectory 'mono_api.c')+'" "'+(Join-Path $moduleDirectory 'mono_collector.c')+'"'),
  'if errorlevel 1 exit /b %errorlevel%',
  'lib.exe /nologo /out:CT2TrainerMonoExisting.lib mono_api.obj mono_collector.obj',
  'if errorlevel 1 exit /b %errorlevel%',
  'cl.exe /nologo /LD /MD mono_api.obj mono_collector.obj /Fe:CT2TrainerMonoExisting.dll /link kernel32.lib /EXPORT:tf_mono_api_select /EXPORT:tf_mono_api_discard /EXPORT:tf_mono_bind_existing /EXPORT:tf_mono_get_jit',
  'if errorlevel 1 exit /b %errorlevel%',
  'dumpbin.exe /imports CT2TrainerMonoExisting.dll > imports.log',
  'if errorlevel 1 exit /b %errorlevel%',
  'dumpbin.exe /headers CT2TrainerMonoExisting.dll > headers.log',
  'exit /b %errorlevel%')
 $batch=Join-Path $output 'build.cmd';[IO.File]::WriteAllLines($batch,$commands,$utf8)
 Push-Location $output
 try {$ErrorActionPreference='Continue';$log=(& cmd.exe /d /c $batch 2>&1|Out-String);$code=$LASTEXITCODE;$ErrorActionPreference='Stop'}finally{Pop-Location}
 [IO.File]::WriteAllText((Join-Path $output 'compiler.log'),$log,$utf8)
 $record=@{architecture=$architecture;exit_code=$code;runtime_spawned=$false;vendor_library_input=$false;dll=(Join-Path $output 'CT2TrainerMonoExisting.dll')}
 $records+=$record
 [IO.File]::WriteAllText((Join-Path $run 'build.json'),(@{schema='ct2trainer-mono-source-only-build/v1';results=$records;runtime_verified=$false;msvc=$installation}|ConvertTo-Json -Depth 8),$utf8)
 if ($code -ne 0) {throw "Source-only compile failed; preserved $output"}
 if ((Get-Content (Join-Path $output 'imports.log') -Raw) -match '(?im)^\s+[\w.-]*mono[\w.-]*\.dll\s*$|^\s+\w+\s+mono_\w+\s*$') {throw 'Unexpected Mono dependency in source-only adapter'}
 $record.dll_sha256=(Get-FileHash -LiteralPath $record.dll -Algorithm SHA256).Hash.ToLowerInvariant()
}
[IO.File]::WriteAllText((Join-Path $run 'build.json'),(@{schema='ct2trainer-mono-source-only-build/v1';results=$records;runtime_verified=$false;msvc=$installation}|ConvertTo-Json -Depth 8),$utf8)
[IO.File]::WriteAllText((Join-Path $draftDirectory 'build/runs/latest-mono-source-build.txt'),$run,$utf8)
Write-Output $run
