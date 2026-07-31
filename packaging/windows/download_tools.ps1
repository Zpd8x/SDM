$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Tools = Join-Path $Root 'Tools'
$Cache = Join-Path $Root 'build\tool-cache'
$FfmpegArchive = Join-Path $Cache 'ffmpeg-release-essentials.zip'
$FfmpegExtract = Join-Path $Cache 'ffmpeg'

New-Item -ItemType Directory -Path $Tools -Force | Out-Null
New-Item -ItemType Directory -Path $Cache -Force | Out-Null

function Download-File {
    param([Parameter(Mandatory=$true)][string]$Uri,[Parameter(Mandatory=$true)][string]$Destination)
    Remove-Item $Destination -Force -ErrorAction SilentlyContinue
    try {
        Write-Host "[TOOLS] Downloading $Uri"
        Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination -TimeoutSec 300
    } catch {
        Write-Host "[TOOLS] Invoke-WebRequest failed; trying curl.exe..."
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if (-not $curl) { throw }
        & $curl.Source -L --fail --retry 3 --connect-timeout 30 -o $Destination $Uri
        if ($LASTEXITCODE -ne 0) { throw "curl.exe failed with exit code $LASTEXITCODE" }
    }
}

function Assert-Executable {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Required executable was not created: $Path" }
    if ((Get-Item $Path).Length -lt 1024) { throw "Downloaded executable is unexpectedly small: $Path" }
}

$YtDlp = Join-Path $Tools 'yt-dlp.exe'
if (-not (Test-Path $YtDlp)) {
    Download-File 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' $YtDlp
}
Assert-Executable $YtDlp

$RequiredFfmpeg = @('ffmpeg.exe', 'ffprobe.exe', 'ffplay.exe')
$MissingFfmpeg = $RequiredFfmpeg | Where-Object { -not (Test-Path (Join-Path $Tools $_)) }
if ($MissingFfmpeg.Count -gt 0) {
    Remove-Item $FfmpegExtract -Recurse -Force -ErrorAction SilentlyContinue
    Download-File 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' $FfmpegArchive
    Write-Host '[TOOLS] Extracting FFmpeg...'
    Expand-Archive -Path $FfmpegArchive -DestinationPath $FfmpegExtract -Force
    $Bin = Get-ChildItem -Path $FfmpegExtract -Directory -Recurse |
        Where-Object { $_.Name -eq 'bin' -and (Test-Path (Join-Path $_.FullName 'ffmpeg.exe')) } |
        Select-Object -First 1
    if (-not $Bin) { throw 'FFmpeg archive was extracted, but its bin directory was not found.' }
    foreach ($Name in $RequiredFfmpeg) {
        Copy-Item (Join-Path $Bin.FullName $Name) (Join-Path $Tools $Name) -Force
    }
}

foreach ($Name in @('yt-dlp.exe') + $RequiredFfmpeg) { Assert-Executable (Join-Path $Tools $Name) }
Write-Host '[TOOLS] All bundled tools are ready:'
Get-ChildItem $Tools -Filter '*.exe' | ForEach-Object { Write-Host ('  - {0} ({1:N1} MB)' -f $_.Name, ($_.Length / 1MB)) }
