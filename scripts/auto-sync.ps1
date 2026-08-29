param(
    [int]$IntervalSeconds = 10
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ScriptPath = Join-Path $RepoRoot 'scripts\auto-sync.ps1'
$BackendPython = Join-Path $RepoRoot 'backend\.venv\Scripts\python.exe'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$MirrorRoots = @('backend', 'frontend', 'scripts', '.github', '.vscode')
Set-Location $RepoRoot

function Write-Status([string]$Message) {
    $timestamp = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$timestamp] $Message"
}

function Update-Dependencies([string[]]$ChangedFiles) {
    if ($ChangedFiles -contains 'backend/requirements.txt') {
        if (Test-Path $BackendPython) {
            Write-Status 'Backend dependencies changed. Updating virtual environment...'
            & $BackendPython -m pip install -r (Join-Path $RepoRoot 'backend\requirements.txt')
            if ($LASTEXITCODE -ne 0) {
                Write-Status 'Warning: backend dependency update failed. Start Dev Stack will retry it.'
            }
        }
        else {
            Write-Status 'Backend dependencies changed. Virtual environment is not created yet; Start Dev Stack will install them.'
        }
    }

    if (($ChangedFiles -contains 'frontend/package.json') -or ($ChangedFiles -contains 'frontend/package-lock.json')) {
        if (Test-Path (Join-Path $FrontendDir 'node_modules')) {
            Write-Status 'Frontend dependencies changed. Updating node_modules...'
            Push-Location $FrontendDir
            try {
                & npm.cmd install --no-package-lock
                if ($LASTEXITCODE -ne 0) {
                    Write-Status 'Warning: frontend dependency update failed. Start Dev Stack will retry it.'
                }
            }
            finally {
                Pop-Location
            }
        }
        else {
            Write-Status 'Frontend dependencies changed. node_modules is not installed yet; Start Dev Stack will install them.'
        }
    }
}

function Remove-UntrackedSource {
    $preview = @(& git clean -nd -- @MirrorRoots)
    if ($LASTEXITCODE -ne 0) {
        throw 'git clean preview failed.'
    }

    if ($preview.Count -gt 0) {
        Write-Status "Removing $($preview.Count) untracked source path(s) so local source matches GitHub main..."
        & git clean -fd -- @MirrorRoots | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw 'git clean failed.'
        }
    }
}

function Restart-Self {
    Write-Status 'Auto-sync script changed. Restarting strict mirror with the new version...'
    Start-Process powershell -WindowStyle Minimized -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $ScriptPath,
        '-IntervalSeconds', [string]$IntervalSeconds
    ) | Out-Null
    exit 0
}

Write-Status "Strict source mirror started for $RepoRoot"
Write-Status "GitHub origin/main is the source of truth. Checking every $IntervalSeconds seconds."
Write-Status 'Tracked local source edits will be overwritten; ignored runtime data is preserved.'

while ($true) {
    try {
        $inside = (& git rev-parse --is-inside-work-tree 2>$null).Trim()
        if ($inside -ne 'true') {
            Write-Status 'This folder is not a Git work tree. Waiting...'
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        $branch = (& git branch --show-current).Trim()
        if ($branch -ne 'main') {
            Write-Status "Current branch is '$branch'. Strict mirror only controls main; waiting..."
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        & git fetch origin main --quiet
        if ($LASTEXITCODE -ne 0) {
            throw 'git fetch failed.'
        }

        $before = (& git rev-parse HEAD).Trim()
        $remote = (& git rev-parse origin/main).Trim()
        $trackedDirty = [bool](& git status --porcelain --untracked-files=no)
        $changed = @()

        if ($before -ne $remote) {
            $changed = @(& git diff --name-only $before $remote)
        }

        if (($before -ne $remote) -or $trackedDirty) {
            if ($trackedDirty) {
                Write-Status 'Tracked local source differs from GitHub. Restoring origin/main...'
            }

            & git reset --hard origin/main | Out-Host
            if ($LASTEXITCODE -ne 0) {
                throw 'git reset --hard origin/main failed.'
            }

            $after = (& git rev-parse HEAD).Trim()
            if ($before -ne $after) {
                Write-Status "Mirrored GitHub source: $($before.Substring(0, 8)) -> $($after.Substring(0, 8))"
            }
            else {
                Write-Status 'Restored tracked source to GitHub main.'
            }
        }

        Remove-UntrackedSource

        if ($changed.Count -gt 0) {
            Update-Dependencies -ChangedFiles $changed

            if ($changed -contains 'scripts/auto-sync.ps1') {
                Restart-Self
            }
        }
    }
    catch {
        Write-Status "Strict mirror warning: $($_.Exception.Message)"
    }

    Start-Sleep -Seconds $IntervalSeconds
}
