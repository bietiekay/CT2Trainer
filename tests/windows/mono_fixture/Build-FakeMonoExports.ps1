$ErrorActionPreference='Stop'
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$developer=Join-Path $installation 'Common7/Tools/VsDevCmd.bat'
$draftDirectory=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$run=Join-Path $draftDirectory ('build/runs/mono-fake-export-build-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $run -ErrorAction Stop)
$commands=@('@echo off',('call "'+$developer+'" -no_logo -arch=x64 -host_arch=x64'),'if errorlevel 1 exit /b %errorlevel%')
foreach($name in @('complete','missing','oldversion','forwarded','data')) {
 $input=Join-Path $draftDirectory ('tests/windows/mono_fixture/fake_exports/'+$name+'.c')
 $link=''
 if($name-eq'forwarded'){$link=' /link /DEF:"'+(Join-Path $draftDirectory 'tests/windows/mono_fixture/fake_exports/forwarded.def')+'"'}
 $commands+=('cl.exe /nologo /W4 /WX /LD /MD /TC "'+$input+'" /Fe:'+($name+'.dll')+$link)
 $commands+='if errorlevel 1 exit /b %errorlevel%'
}
$moduleDirectory=Join-Path $draftDirectory 'src/ct2trainer/native/mono'
$includeDirectory=Join-Path $draftDirectory 'dependencies/native/mono-api-source/upstream'
$probe=Join-Path $draftDirectory 'tests/windows/mono_fixture/fake_exports/admission_probe.c'
$commands+=('cl.exe /nologo /W4 /WX /LD /MD /TC /I"'+$moduleDirectory+'" /I"'+$includeDirectory+'" "'+$probe+'" /Fe:admission_probe.dll')
$commands+='if errorlevel 1 exit /b %errorlevel%'
$commands+='exit /b %errorlevel%'
$batch=Join-Path $run 'build.cmd';[IO.File]::WriteAllLines($batch,$commands,[Text.UTF8Encoding]::new($false))
Push-Location $run
try{$ErrorActionPreference='Continue';$text=(& cmd.exe /d /c $batch 2>&1|Out-String);$code=$LASTEXITCODE;$ErrorActionPreference='Stop'}finally{Pop-Location}
[IO.File]::WriteAllText((Join-Path $run 'compiler.log'),$text,[Text.UTF8Encoding]::new($false))
if($code-ne0){throw "Fake exports compile failed; retained $run"}
[IO.File]::WriteAllText((Join-Path $draftDirectory 'build/runs/latest-mono-fake-export-build.txt'),$run,[Text.UTF8Encoding]::new($false))
Write-Output $run
