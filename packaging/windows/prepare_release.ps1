$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Release = Join-Path $Root 'release'
$Dist = Join-Path $Root 'build\windows\SDM'
$PortableStage = Join-Path $Root 'build\portable\SDM_v2.0.0_Portable_x64'

if (-not (Test-Path $Dist)) { throw "PyInstaller output not found: $Dist" }
Remove-Item (Join-Path $Root 'build\portable') -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $PortableStage -Force | Out-Null
Copy-Item "$Dist\*" $PortableStage -Recurse -Force
Copy-Item (Join-Path $Root 'browser_extension') $PortableStage -Recurse -Force
New-Item -ItemType Directory -Path (Join-Path $PortableStage 'browser_host') -Force | Out-Null
Copy-Item (Join-Path $Root 'build\windows\native_host\SDMNativeHost.exe') (Join-Path $PortableStage 'browser_host\SDMNativeHost.exe') -Force
Copy-Item (Join-Path $Root 'README.md') $PortableStage -Force
Copy-Item (Join-Path $Root 'CHANGELOG.md') $PortableStage -Force
Copy-Item (Join-Path $Root 'BROWSER_SETUP_AR.md') $PortableStage -Force
Copy-Item (Join-Path $Root 'LICENSE.txt') $PortableStage -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $Root 'Tools') $PortableStage -Recurse -Force

New-Item -ItemType Directory -Path $Release -Force | Out-Null
$PortableZip = Join-Path $Release 'SDM_v2.0.0_Portable_x64.zip'
Remove-Item $PortableZip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $PortableStage -DestinationPath $PortableZip -CompressionLevel Optimal

$ExtensionZip = Join-Path $Release 'SDM_Browser_Extension_v2.0.0.zip'
Remove-Item $ExtensionZip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $Root 'browser_extension\*') -DestinationPath $ExtensionZip -CompressionLevel Optimal
Copy-Item (Join-Path $Root 'RELEASE_NOTES.md') $Release -Force
