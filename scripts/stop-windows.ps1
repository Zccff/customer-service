$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
if (Test-Path -LiteralPath (Join-Path $projectRoot 'data/classifier-windows.json')) {
    & $pythonExe -m scripts.windows_job_runner classifier-down
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Classifier was not stopped; check its ownership record.' }
}
foreach ($name in @('app','mcp-logistics','mcp-aftersales')) {
    $pidFile = Join-Path $projectRoot ('data/' + $name + '.pid')
    if (!(Test-Path -LiteralPath $pidFile)) { continue }
    $servicePid = [int](Get-Content -LiteralPath $pidFile)
    $process = Get-Process -Id $servicePid -ErrorAction SilentlyContinue
    if ($process -and $process.Path -eq $pythonExe) {
        $runtimeRoot = Join-Path $projectRoot '.runtime-python\'
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$servicePid" | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.StartsWith($runtimeRoot, [StringComparison]::OrdinalIgnoreCase)
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $servicePid -ErrorAction SilentlyContinue
        Write-Host ($name + ' stopped.')
    }
    Remove-Item -LiteralPath $pidFile
}
Write-Host 'Application processes stopped. Docker data services remain running.'
