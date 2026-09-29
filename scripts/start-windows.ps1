$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = $projectRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonExe)) { throw 'Missing .venv. Install dependencies first.' }
if (!(Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) { throw 'Missing .env.' }

docker compose up -d --wait --wait-timeout 240
if ($LASTEXITCODE -ne 0) { throw 'Docker services are not ready. Open Docker Desktop and inspect docker compose ps.' }
$monitoringEnabled = & $pythonExe -c "from app.core.observability import langfuse_enabled; print('yes' if langfuse_enabled() else 'no')"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read monitoring configuration.' }
if ($monitoringEnabled -eq 'yes') {
    docker compose -p mewhelp-langfuse -f docker-compose.langfuse.yml -f docker-compose.langfuse.local.yml up -d
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Local monitoring failed to start. Inspect its Docker logs.' }
}
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'log') | Out-Null

$services = @(
    @{ Name='mcp-logistics'; Port=8101; Arguments=@('-m','mcp_servers.logistics_server') },
    @{ Name='mcp-aftersales'; Port=8102; Arguments=@('-m','mcp_servers.aftersales_server') },
    @{ Name='app'; Port=8000; Arguments=@('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') }
)
foreach ($service in $services) {
    $pidFile = Join-Path $projectRoot ('data/' + $service.Name + '.pid')
    if (Test-Path -LiteralPath $pidFile) {
        $existingPid = [int](Get-Content -LiteralPath $pidFile)
        $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existingProcess -and $existingProcess.Path -eq $pythonExe) {
            Write-Host ($service.Name + ' is running or initializing.')
            continue
        }
    }
    $listener = Get-NetTCPConnection -State Listen -LocalPort $service.Port -ErrorAction SilentlyContinue
    if ($listener) {
        $savedPid = if (Test-Path -LiteralPath $pidFile) { [int](Get-Content -LiteralPath $pidFile) } else { 0 }
        $childPids = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$savedPid" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ProcessId)
        if ($savedPid -and (@($listener.OwningProcess | Where-Object { $_ -eq $savedPid -or $_ -in $childPids }).Count -gt 0)) {
            Write-Host ($service.Name + ' is already running.')
            continue
        }
        throw ('Port ' + $service.Port + ' is occupied by another process.')
    }
    $process = Start-Process -FilePath $pythonExe -ArgumentList $service.Arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot ('log/' + $service.Name + '.stdout.log')) -RedirectStandardError (Join-Path $projectRoot ('log/' + $service.Name + '.stderr.log'))
    Set-Content -LiteralPath $pidFile -Value $process.Id
    Write-Host ($service.Name + ' started: ' + $process.Id)
}
$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (!$ready) { throw 'Application did not become ready. Inspect log/app.stderr.log.' }
Write-Host 'Ready: http://localhost:8000'
if (Test-Path -LiteralPath (Join-Path $projectRoot 'data/ch10/onnx/model.onnx')) {
    & $pythonExe -m scripts.windows_job_runner classifier-up
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Classifier startup failed. Inspect log/classifier.log.' }
}
