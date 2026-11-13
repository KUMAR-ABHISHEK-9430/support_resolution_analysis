param([string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin', [switch]$Stop)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$clusterPath = Join-Path $projectRoot 'documentation\evidence\postgres_cluster'
if ($Stop) {
    & "$PgBin\pg_ctl.exe" -D $clusterPath -m fast -w stop
    exit $LASTEXITCODE
}
# Dedicated local cluster: do not touch the user's installed service or databases.
if (-not (Test-Path (Join-Path $clusterPath 'PG_VERSION'))) {
    & "$PgBin\initdb.exe" -D $clusterPath -U portfolio --auth-local=trust --auth-host=trust --encoding=UTF8 --locale=C
    if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
}
& "$PgBin\pg_ctl.exe" -D $clusterPath status
if ($LASTEXITCODE -ne 0) {
    $logPath = Join-Path $projectRoot 'documentation\evidence\postgres.log'
    & "$PgBin\pg_ctl.exe" -D $clusterPath -l $logPath -o '-p 55432 -h 127.0.0.1' -w start
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL start failed' }
}
Write-Output 'Project-only local connection: postgresql://portfolio@127.0.0.1:55432/postgres'
