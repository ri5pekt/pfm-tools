Write-Host "=== Docker Containers ===" -ForegroundColor Cyan
docker-compose ps

Write-Host "`n=== Docker Container Status ===" -ForegroundColor Cyan
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Out-String

Write-Host "`n=== Frontend Dependencies ===" -ForegroundColor Cyan
if (Test-Path "frontend\node_modules") {
    Write-Host "node_modules exists" -ForegroundColor Green
} else {
    Write-Host "node_modules NOT found - installing..." -ForegroundColor Yellow
    cd frontend
    npm install
    cd ..
}

Write-Host "`n=== Port Status ===" -ForegroundColor Cyan
$ports = @(5173, 8001, 5434, 6380)
foreach ($port in $ports) {
    $listening = netstat -ano | Select-String ":$port " | Select-Object -First 1
    if ($listening) {
        Write-Host "Port $port is listening" -ForegroundColor Green
    } else {
        Write-Host "Port $port is NOT listening" -ForegroundColor Red
    }
}

