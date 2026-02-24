$ErrorActionPreference = "SilentlyContinue"

$targets = Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "uvicorn app\.main:app" -and $_.CommandLine -match "127\.0\.0\.1" }

if (-not $targets) {
  Write-Host "No local server process found."
  exit 0
}

foreach ($proc in $targets) {
  Stop-Process -Id $proc.ProcessId -Force
  Write-Host "Stopped PID=$($proc.ProcessId)"
}
