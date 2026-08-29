param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$BackendPython = Join-Path $BackendDir '.venv\Scripts\python.exe'

function Write-Status([string]$Message) {
    $timestamp = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$timestamp] $Message"
}

function Stop-ProjectListener([int]$Port, [string]$ExpectedPattern) {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
        $commandLine = if ($processInfo) { [string]$processInfo.CommandLine } else { '' }

        if ($commandLine -match $ExpectedPattern) {
            Write-Status "Stopping stale project process on port $Port (PID $($listener.OwningProcess))."
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
            continue
        }

        $name = if ($processInfo) { $processInfo.Name } else { 'unknown process' }
        throw "Port $Port is already used by $name (PID $($listener.OwningProcess)). Close it or change the project port."
    }
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

Write-Host ''
Write-Host 'Social Publisher - One Click Dev' -ForegroundColor Cyan
Write-Host '--------------------------------' -ForegroundColor DarkGray
Write-Status "Repository: $RepoRoot"

# Clean up only known project development servers. Do not kill unrelated apps.
Stop-ProjectListener -Port 8765 -ExpectedPattern 'uvicorn\s+app\.main:app'
Stop-ProjectListener -Port 5173 -ExpectedPattern '(vite|node_modules[\\/]vite)'

if (-not (Test-Path $BackendPython)) {
    Write-Status 'Creating Python 3.12 virtual environment...'
    Push-Location $BackendDir
    try {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Unable to create backend virtual environment.' }
    }
    finally {
        Pop-Location
    }
}

# Install dependencies only when the environment cannot import the application.
& $BackendPython -c "import fastapi, uvicorn, sqlalchemy, selenium, multipart, ixbrowser_local_api" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Status 'Installing backend dependencies...'
    & $BackendPython -m pip install -r (Join-Path $BackendDir 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
}

if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Write-Status 'Installing frontend dependencies...'
    Push-Location $FrontendDir
    try {
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    }
    finally {
        Pop-Location
    }
}

# Keep GitHub auto-sync alive even when the project is launched outside VS Code.
$syncRunning = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -like '*auto-sync.ps1*' -and $_.CommandLine -like "*$RepoRoot*"
} | Select-Object -First 1

if (-not $syncRunning) {
    Write-Status 'Starting GitHub auto-sync...'
    Start-Process powershell -WindowStyle Minimized -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', (Join-Path $RepoRoot 'scripts\auto-sync.ps1'),
        '-IntervalSeconds', '10'
    ) | Out-Null
}
else {
    Write-Status 'GitHub auto-sync is already running.'
}

$backendCommand = "Set-Location '$BackendDir'; `$Host.UI.RawUI.WindowTitle = 'Social Publisher Backend'; & '$BackendPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload"
$frontendCommand = "Set-Location '$FrontendDir'; `$Host.UI.RawUI.WindowTitle = 'Social Publisher Frontend'; npm.cmd run dev"

Write-Status 'Starting backend on http://127.0.0.1:8765 ...'
Start-Process powershell -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $backendCommand) | Out-Null

Write-Status 'Starting frontend on http://127.0.0.1:5173 ...'
Start-Process powershell -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $frontendCommand) | Out-Null

$backendReady = Wait-Http -Url 'http://127.0.0.1:8765/health' -TimeoutSeconds 30
$frontendReady = Wait-Http -Url 'http://127.0.0.1:5173/' -TimeoutSeconds 30

if ($backendReady) {
    Write-Status 'Backend ready.'
}
else {
    Write-Warning 'Backend did not become ready within 30 seconds. Check the Backend window.'
}

if ($frontendReady) {
    Write-Status 'Frontend ready.'
}
else {
    Write-Warning 'Frontend did not become ready within 30 seconds. Check the Frontend window.'
}

if ($backendReady -and $frontendReady -and -not $NoBrowser) {
    Write-Status 'Opening Social Publisher...'
    Start-Process 'http://127.0.0.1:5173/'
}

Write-Host ''
Write-Status 'Development stack launch finished.'
