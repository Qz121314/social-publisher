param(
    [int]$IntervalSeconds = 10
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepoRoot

function Write-Status([string]$Message) {
    $timestamp = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$timestamp] $Message"
}

Write-Status "Auto-sync started for $RepoRoot"
Write-Status "Watching origin/main every $IntervalSeconds seconds. Local edits pause pulling automatically."

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
            Write-Status "Current branch is '$branch'. Auto-sync only follows main; waiting..."
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        $dirty = & git status --porcelain
        if ($dirty) {
            Write-Status 'Local changes detected. Auto-pull paused to protect your work.'
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        & git fetch origin main --quiet
        if ($LASTEXITCODE -ne 0) {
            throw 'git fetch failed.'
        }

        $local = (& git rev-parse HEAD).Trim()
        $remote = (& git rev-parse origin/main).Trim()

        if ($local -eq $remote) {
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        & git merge-base --is-ancestor HEAD origin/main
        if ($LASTEXITCODE -ne 0) {
            Write-Status 'Local main has diverged from origin/main. Auto-pull stopped for safety; resolve Git history manually.'
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        $before = $local
        & git pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) {
            throw 'git pull --ff-only failed.'
        }

        $after = (& git rev-parse HEAD).Trim()
        Write-Status "Updated local project: $($before.Substring(0, 8)) -> $($after.Substring(0, 8))"

        $changed = & git diff --name-only "$before..$after"
        if ($changed -contains 'backend/requirements.txt') {
            Write-Status 'backend/requirements.txt changed. Re-run: python -m pip install -r backend/requirements.txt'
        }
        if (($changed -contains 'frontend/package.json') -or ($changed -contains 'frontend/package-lock.json')) {
            Write-Status 'Frontend dependencies changed. Re-run npm install inside frontend.'
        }
    }
    catch {
        Write-Status "Auto-sync warning: $($_.Exception.Message)"
    }

    Start-Sleep -Seconds $IntervalSeconds
}
