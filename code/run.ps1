param([switch]$WithPostgres, [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Push-Location $projectRoot
try {
    foreach ($step in @('ingest.py','explore.py','clean.py','analyze.py','validate.py')) {
        Write-Output "Running $step"
        & $pythonPath (Join-Path $PSScriptRoot $step)
        if ($LASTEXITCODE -ne 0) { throw "$step failed" }
    }
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    & $pythonPath -m pytest -c code/pytest.ini code/tests -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    if ($WithPostgres) {
        & (Join-Path $PSScriptRoot 'bootstrap_db.ps1') -PgBin $PgBin
        if ($LASTEXITCODE -ne 0) { throw 'Database bootstrap failed' }
        $env:DATABASE_URL = 'postgresql://portfolio@127.0.0.1:55432/postgres'
        & $pythonPath (Join-Path $PSScriptRoot 'load_postgres.py')
        if ($LASTEXITCODE -ne 0) { throw 'Database validation failed' }
    }
} finally {
    Pop-Location
}
