$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Release = Join-Path $Root 'release'
$Output = Join-Path $Release 'SHA256SUMS.txt'
$Lines = Get-ChildItem $Release -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object Name | ForEach-Object {
    $Hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  $($_.Name)"
}
Set-Content -Path $Output -Value $Lines -Encoding ascii
