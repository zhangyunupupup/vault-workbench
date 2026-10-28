$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Join-Path $projectDir 'runtime'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
try {
    $serverInfoFile = Join-Path $runtimeDir 'server.json'
    if (Test-Path -LiteralPath $serverInfoFile) {
        $savedServer = Get-Content -LiteralPath $serverInfoFile -Raw | ConvertFrom-Json
        $serverUrl = [Uri]$savedServer.url
        if ($serverUrl.Host -eq '127.0.0.1' -and $serverUrl.Port -ge 8765 -and $serverUrl.Port -le 8774) {
            $healthRequest = [System.Net.HttpWebRequest]::Create($savedServer.url + '/api/health')
            $healthRequest.Proxy = $null
            $healthRequest.Timeout = 1500
            $healthResponse = $healthRequest.GetResponse()
            $healthReader = New-Object System.IO.StreamReader($healthResponse.GetResponseStream())
            try { $health = $healthReader.ReadToEnd() | ConvertFrom-Json }
            finally { $healthReader.Dispose(); $healthResponse.Dispose() }
            if ($health.app -eq 'vault-workbench' -and $health.project -eq $projectDir) {
                Start-Process $savedServer.url
                exit 0
            }
        }
    }
} catch { }
$pythonCandidates = @(
    (Join-Path $projectDir 'python\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)
$pythonExecutable = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        & $candidate -c 'import http.server, socket, zipfile, sys; assert sys.version_info >= (3,10)' 2>$null
        if ($LASTEXITCODE -eq 0) { $pythonExecutable = $candidate; break }
    }
}
if (-not $pythonExecutable) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        & $pythonCommand.Source -c 'import http.server, socket, zipfile, sys; assert sys.version_info >= (3,10)' 2>$null
        if ($LASTEXITCODE -eq 0) { $pythonExecutable = $pythonCommand.Source }
    }
}
if (-not $pythonExecutable) { throw '未找到可用的 Python 3.10+。安装 Python 后重新双击启动即可。' }
$env:PYTHONIOENCODING = 'utf-8'
Start-Process -FilePath $pythonExecutable -ArgumentList @('-X', 'utf8', '-u', ('"' + (Join-Path $projectDir 'server.py') + '"'), '--open') -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDir 'server.log') -RedirectStandardError (Join-Path $runtimeDir 'error.log')
Write-Output 'VAULT 工作台已启动，正在打开浏览器。'
