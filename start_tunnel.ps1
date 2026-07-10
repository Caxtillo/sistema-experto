$host.UI.RawUI.WindowTitle = "Cloudflare Tunnel"
$url = $null

while ($true) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Iniciando cloudflared..." -ForegroundColor Cyan
    $tmpFile = [System.IO.Path]::GetTempFileName()
    
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cloudflared"
    $psi.Arguments = "tunnel --url http://localhost:8000 --no-autoupdate"
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    
    $outputBuilder = New-Object System.Text.StringBuilder
    
    Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -Action {
        $line = $EventArgs.Data
        if ($line) {
            $outputBuilder.AppendLine($line) | Out-Null
            if ($line -match 'https://([a-z0-9-]+)\.trycloudflare\.com') {
                $script:url = $matches[0]
                Write-Host ""
                Write-Host "========================================" -ForegroundColor Green
                Write-Host "  Tunnel URL: $script:url" -ForegroundColor White -BackgroundColor DarkGreen
                Write-Host "========================================" -ForegroundColor Green
                Write-Host ""
                Write-Host "  Abre en tu navegador: $script:url" -ForegroundColor Yellow
                Write-Host ""
            }
        }
    } | Out-Null
    
    Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived -Action {
        $line = $EventArgs.Data
        if ($line) {
            $outputBuilder.AppendLine($line) | Out-Null
            if ($line -match 'https://([a-z0-9-]+)\.trycloudflare\.com') {
                $script:url = $matches[0]
                Write-Host ""
                Write-Host "========================================" -ForegroundColor Green
                Write-Host "  Tunnel URL: $script:url" -ForegroundColor White -BackgroundColor DarkGreen
                Write-Host "========================================" -ForegroundColor Green
                Write-Host ""
                Write-Host "  Abre en tu navegador: $script:url" -ForegroundColor Yellow
                Write-Host ""
            }
        }
    } | Out-Null
    
    $proc.Start() | Out-Null
    $proc.BeginOutputReadLine()
    $proc.BeginErrorReadLine()
    
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Esperando URL del tunnel..." -ForegroundColor Cyan
    
    $proc.WaitForExit()
    
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] cloudflared se detuvo, reiniciando en 3s..." -ForegroundColor Red
    Start-Sleep -Seconds 3
}
