#requires -Version 5.1
<# Independent edition: archived Python, PyInstaller, NASM, iced-x86 and Lua53; no CE inputs. #>
[CmdletBinding()]
param([string]$Python = '', [string]$OutputRoot = 'build/runs')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $repo
if (-not $Python) {
    $Python = Join-Path $repo '.tools/python/python.exe'
    if (-not (Test-Path -LiteralPath $Python)) {
        $archive = Join-Path $repo 'dependencies/python/python-3.12.14-windows-x64-portable.zip'
        $manifest = Get-Content -LiteralPath (Join-Path $repo 'dependencies/manifest.json') -Raw | ConvertFrom-Json
        $entry = $manifest.files | Where-Object { $_.path -eq 'python/python-3.12.14-windows-x64-portable.zip' }
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw 'Archived Python hash mismatch.' }
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $repo '.tools/python')
    }
}
$pythonPath = (Get-Command $Python -CommandType Application -ErrorAction Stop).Source
& $pythonPath -c 'import sys; assert sys.platform == ''win32'' and sys.maxsize > 2**32 and sys.version_info[:2] == (3,12), ''Archived native wheels require Windows x64 Python 3.12'''
if ($LASTEXITCODE -ne 0) { throw 'Unsupported Python runtime.' }
$runId = 'native-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$run = Join-Path ([IO.Path]::GetFullPath($OutputRoot)) $runId
New-Item -ItemType Directory -Path $run | Out-Null
$env:PYTHONPATH = Join-Path $repo 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
Start-Transcript -Path (Join-Path $run 'build.log') | Out-Null
try {
    # Verify only the inputs used by this edition, without reading CE payloads.
    & $pythonPath tools/native_build.py verify-inputs
    if ($LASTEXITCODE -ne 0) { throw 'Native build input verification failed.' }
    & $pythonPath -m venv (Join-Path $run 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create native build environment.' }
    $buildPython = Join-Path $run 'venv/Scripts/python.exe'
    & $buildPython -m pip install --no-index --find-links dependencies/python/wheels -r dependencies/python/requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Offline PyInstaller installation failed.' }
    & $buildPython -m pip install --no-index --find-links dependencies/native/lupa --find-links dependencies/native/iced-x86 lupa==2.8 iced-x86==1.21.0
    if ($LASTEXITCODE -ne 0) { throw 'Offline BSD/MIT native runtime installation failed.' }
    & $buildPython tools/native_build.py restore-nasm --output (Join-Path $run 'test-native-tools')
    if ($LASTEXITCODE -ne 0) { throw 'Archived NASM restoration failed.' }
    $env:CT2TRAINER_NASM = Join-Path $run 'test-native-tools/nasm.exe'
    & $buildPython tools/native_build.py run-tests --output $run
    if ($LASTEXITCODE -ne 0) { throw 'Independent edition tests failed.' }
    & $buildPython tools/native_build.py build --output $run
    if ($LASTEXITCODE -ne 0) { throw "Native build failed; inspect $run" }
    Write-Output "Native edition built: $run"
} finally { Stop-Transcript | Out-Null }
