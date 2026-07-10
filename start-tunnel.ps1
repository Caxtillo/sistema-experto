$serverDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$tunnelUrlFile = Join-Path $serverDir "tunnel_url.txt"
Remove-Item $tunnelUrlFile -ErrorAction SilentlyContinue

# Start the uvicorn server
$env:SECRET_KEY = 'test-secret-key'
$env:PYTHONUTF8 = '1'
$server = Start-Process -FilePath "python3.13" -ArgumentList "-m uvicorn app:app --host 0.0.0.0 --port 8000" -WorkingDirectory $serverDir -WindowStyle Hidden -PassThru
Write-Output "Server started (PID $($server.Id))"

Start-Sleep 4

# Start cloudflared tunnel, capture output to get the URL
$logFile = Join-Path $serverDir "tunnel_log.txt"
$tunnel = Start-Process -FilePath "C:\Program Files (x86)\cloudflared\cloudflared.exe" -ArgumentList "tunnel --url http://localhost:8000" -WindowStyle Hidden -RedirectStandardOutput $logFile -PassThru
Write-Output "Tunnel started (PID $($tunnel.Id))"

# Wait for tunnel URL to appear in log
$url = $null
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep 1
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw
        $match = [regex]::Match($content, 'https://[a-z-]+\.trycloudflare\.com')
        if ($match.Success) {
            $url = $match.Value
            break
        }
    }
}

if ($url) {
    $url | Out-File -FilePath $tunnelUrlFile
    Write-Output "Tunnel URL: $url"
    Remove-Item $logFile -ErrorAction SilentlyContinue
} else {
    Write-Output "Failed to get tunnel URL - check tunnel_log.txt for errors"
}
