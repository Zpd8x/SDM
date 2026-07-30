$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Tools = Join-Path $Root 'Tools'
$Cache = Join-Path $Root 'build\tool-cache'
$FfmpegArchive = Join-Path $Cache 'ffmpeg-release-essentials.zip'
$FfmpegExtract = Join-Path $Cache 'ffmpeg'

New-Item -ItemType Directory -Path $Tools -Force | Out-Null
New-Item -ItemType Directory -Path $Cache -Force | Out-Null

function Assert-Executable {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) {
        throw "Required executable was not created: $Path"
    }
    if ((Get-Item $Path).Length -lt 1024) {
        throw "Downloaded executable is unexpectedly small: $Path"
    }
}

$YtDlp = Join-Path $Tools 'yt-dlp.exe'
if (-not (Test-Path $YtDlp)) {
    Write-Host '[TOOLS] Downloading yt-dlp.exe...'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' -OutFile $YtDlp
}
Assert-Executable $YtDlp

$RequiredFfmpeg = @('ffmpeg.exe', 'ffprobe.exe', 'ffplay.exe')
$MissingFfmpeg = $RequiredFfmpeg | Where-Object { -not (Test-Path (Join-Path $Tools $_)) }
if ($MissingFfmpeg.Count -gt 0) {
    Write-Host '[TOOLS] Downloading FFmpeg essentials build...'
    Remove-Item $FfmpegArchive -Force -ErrorAction SilentlyContinue
    Remove-Item $FfmpegExtract -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -UseBasicParsing -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $FfmpegArchive
    Expand-Archive -Path $FfmpegArchive -DestinationPath $FfmpegExtract -Force

    $Bin = Get-ChildItem -Path $FfmpegExtract -Directory -Recurse |
        Where-Object { $_.Name -eq 'bin' -and (Test-Path (Join-Path $_.FullName 'ffmpeg.exe')) } |
        Select-Object -First 1
    if (-not $Bin) {
        throw 'FFmpeg archive was extracted, but its bin directory was not found.'
    }
    foreach ($Name in $RequiredFfmpeg) {
        Copy-Item (Join-Path $Bin.FullName $Name) (Join-Path $Tools $Name) -Force
    }
}

foreach ($Name in @('yt-dlp.exe') + $RequiredFfmpeg) {
    Assert-Executable (Join-Path $Tools $Name)
}

Write-Host '[TOOLS] All bundled tools are ready:'
Get-ChildItem $Tools -Filter '*.exe' | ForEach-Object {
    Write-Host ('  - {0} ({1:N1} MB)' -f $_.Name, ($_.Length / 1MB))
}
