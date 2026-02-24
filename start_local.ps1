$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

Write-Host "[1/2] Apply database migrations..."
alembic upgrade head

Write-Host "[2/2] Start server on http://127.0.0.1:8000"
Write-Host "Keep this window open. Press Ctrl+C to stop."

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
