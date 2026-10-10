#requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Index, [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$indexPath = (Resolve-Path $Index).Path
$definition = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
$base = Split-Path -Parent $indexPath
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory for historical evidence.' }
New-Item -ItemType Directory -Path $output | Out-Null
$zip = Join-Path $output $definition.archive
if ($definition.parts) {
    $stream = [IO.File]::Open($zip, [IO.FileMode]::CreateNew)
    try {
        foreach ($part in $definition.parts) {
            $path = Join-Path $base $part.path
            if ((Get-Item -LiteralPath $path).Length -ne $part.bytes -or
                (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $part.sha256) { throw "Archive part mismatch: $path" }
            $input = [IO.File]::OpenRead($path)
            try { $input.CopyTo($stream) } finally { $input.Dispose() }
        }
    } finally { $stream.Dispose() }
} else { Copy-Item -LiteralPath (Join-Path $base $definition.archive) -Destination $zip }
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -cne $definition.sha256) { throw 'Archive hash mismatch' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($zip, (Join-Path $output 'contents'))
Write-Output "Historical evidence restored to $output/contents"
