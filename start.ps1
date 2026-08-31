param(
    [switch]$Install,
    [switch]$CreateDB,
    [switch]$Run
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$venvPath = Join-Path $scriptDir '.venv'
$activate = Join-Path $venvPath 'Scripts\Activate.ps1'

if (-not (Test-Path $activate)) {
    python -m venv .venv
}
. $activate

if ($Install) {
    python -m ensurepip --upgrade
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
}

# Safe default: start the app without deleting the existing database.
if (-not ($CreateDB -or $Run)) {
    $Run = $true
}

if ($CreateDB) {
    Write-Warning 'create_db.py resets instance/hms.db. Existing data will be deleted.'
    python create_db.py
}

if ($Run) {
    python run.py
}
