$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

$cmd = "Set-Location '$PSScriptRoot'; alembic upgrade head; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process -FilePath powershell -ArgumentList @("-NoExit", "-Command", $cmd)

Write-Host "Started a new PowerShell window for the server."
Write-Host "Health URL: http://127.0.0.1:8000/health"
