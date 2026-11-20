$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir 'venv\Scripts\python.exe'

if (-not (Test-Path $VenvPython)) {
  Write-Error "No se encontró el entorno virtual en '$VenvPython'."
  exit 1
}

Push-Location $ScriptDir
try {
  & $VenvPython -m uvicorn app.main:app --reload --port 8000
} finally {
  Pop-Location
}
