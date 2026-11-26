# Backup of DUP Presenter user data that is NOT in git.
#
# Copies:  decks/ (if untracked edits exist), work/ (licence + attribution metadata,
#          storyboard approvals, history), public/uploads/ (dropped assets),
#          public/models3d/ (generated .glb models).
# Never copies: secrets/ and .env (API keys must not spread to more disks).
#
# Usage (run from anywhere):
#   powershell -ExecutionPolicy Bypass -File scripts\backup_user_data.ps1 -Destination "D:\DUP_backup"
#
# Each run creates a timestamped folder under -Destination. Nothing is deleted.

param(
    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$target = Join-Path $Destination "dup-presenter_$stamp"

$sources = @(
    @{ Src = Join-Path $root "decks";           Dst = "decks" },
    @{ Src = Join-Path $root "work";            Dst = "work" },
    @{ Src = Join-Path $root "public\uploads";  Dst = "public\uploads" },
    @{ Src = Join-Path $root "public\models3d"; Dst = "public\models3d" }
)

New-Item -ItemType Directory -Force -Path $target | Out-Null

$copied = 0
foreach ($s in $sources) {
    if (-not (Test-Path $s.Src)) {
        Write-Host "[skip] $($s.Dst) (not present)"
        continue
    }
    $dst = Join-Path $target $s.Dst
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    # /E copy subdirectories incl. empty, /R:2 /W:2 retry briefly on locked files, /NFL /NDL quiet listing
    & robocopy $s.Src $dst /E /R:2 /W:2 /NFL /NDL /NJH /NJS | Out-Null
    # robocopy exit codes 0-7 are success (bit flags); >= 8 means failure
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed for $($s.Src) with exit code $LASTEXITCODE"
    }
    $copied++
    Write-Host "[ok]   $($s.Dst) -> $dst"
}

if ($copied -eq 0) {
    throw "Nothing to back up under $root"
}

Write-Host "Backup complete: $target"
