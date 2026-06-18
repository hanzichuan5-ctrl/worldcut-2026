Get-Content "D:\heart\.env" | ForEach-Object {
    if ($_ -match '^\s*([^#=][^=]*)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2], 'Process')
    }
}
$port = if ($env:PORT) { $env:PORT } else { 8765 }
$url = "http://127.0.0.1:$port/"
$proc = Start-Process -FilePath "D:\python\python.exe" -ArgumentList '"D:\heart\server.py"' -PassThru -NoNewWindow
for ($i = 0; $i -lt 30; $i++) {
    try {
        Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1 | Out-Null
        break
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
Start-Process $url
Wait-Process -Id $proc.Id
