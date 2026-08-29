# Social Publisher

Local-first multi-account social publishing system built around iXBrowser profiles.

## Goal

Manage multiple social accounts, schedule content, and execute publishing jobs through isolated iXBrowser profiles. Platform-specific automation is implemented through adapters so Facebook, Instagram, X, TikTok, Threads and other platforms can be added without changing the scheduler core.

## Architecture

- **Frontend:** React + TypeScript + Vite
- **Backend:** Python 3.12 + FastAPI
- **Database:** SQLite + SQLAlchemy
- **Browser layer:** iXBrowser Local API + Selenium 4
- **Scheduling:** APScheduler / worker layer
- **Platform layer:** independent adapters per platform

## Current milestone

The repository currently includes:

- FastAPI backend and Vite/React local admin
- iXBrowser Local API health check and paginated profile discovery
- SQLite database initialization on backend startup
- Cached `browser_profiles` table for iX environments
- Generic `accounts` table for multi-platform account bindings
- iX profile sync into SQLite
- Account create, list, edit, enable/disable and delete APIs
- Local account-management interface
- iX profile open/close lifecycle through the official Local API
- Selenium 4 attachment using the `webdriver` and `debugging_address` returned by iXBrowser
- Live Selenium session health checks and current page/title reporting
- Browser-control UI for Open, Check and Close actions

A single iX profile can be linked to different platforms, while the same profile cannot be linked twice to the same platform.

## Database

The database is created automatically at:

```text
data/social_publisher.db
```

Runtime database files are excluded from Git.

Main tables:

```text
browser_profiles
accounts
```

`browser_profiles` is a local cache of iXBrowser profiles. `accounts` stores the platform account binding and references `ix_profile_id`.

## Local API

iXBrowser Local API defaults to:

```text
http://127.0.0.1:53200/api/v2/
```

The iXBrowser desktop client must be running and Local API must be enabled before profile sync or browser lifecycle operations can succeed.

## Backend development

From the repository root:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

Backend health check:

```text
http://127.0.0.1:8765/health
```

FastAPI documentation:

```text
http://127.0.0.1:8765/docs
```

## Frontend development

Open another PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Then open:

```text
http://127.0.0.1:5173
```

Vite proxies `/api` and `/health` to the FastAPI process on port `8765`.

## Browser workflow

1. Start iXBrowser and enable Local API.
2. Start the backend and frontend.
3. Open the local admin.
4. Click **Sync iX Profiles**.
5. In **iXBrowser profiles**, click **Open** on a profile.
6. The backend opens the iX profile and attaches Selenium to the returned debugging address.
7. Click **Check** to verify Selenium can still read the browser title, URL and window list.
8. Click **Close** to close the iX profile and stop the local WebDriver service.

Live Selenium sessions are currently stored in backend process memory. If the FastAPI process is restarted, the in-memory session registry is lost even if an iX window remains open. The next milestone adds profile locking, ownership and recovery behavior for worker execution.

## Account workflow

1. Sync iX profiles.
2. Select an iX profile and platform.
3. Create the account binding.
4. Enable/disable, edit or delete bindings from the account table.

## API endpoints

```text
GET    /api/status
GET    /api/ixbrowser/profiles
POST   /api/ixbrowser/sync
GET    /api/browser-profiles
GET    /api/browser-sessions
POST   /api/browser-profiles/{profile_id}/open
POST   /api/browser-profiles/{profile_id}/probe
POST   /api/browser-profiles/{profile_id}/close
GET    /api/accounts
POST   /api/accounts
PATCH  /api/accounts/{account_id}
DELETE /api/accounts/{account_id}
```

## Development milestones

1. Project skeleton and local web admin — done
2. iXBrowser Local API connectivity and profile sync — done
3. SQLite and account management — done
4. Selenium attach/open/close lifecycle — done
5. Profile locking and worker execution model
6. Facebook single-account publishing proof of concept
7. Media publishing and verification
8. Scheduled jobs and multi-account worker pool
9. Batch scheduling and execution history
10. Additional platform adapters

## Security

Never commit social-account passwords, cookies, API tokens, proxy credentials, or other secrets to Git. Runtime data and `.env` files are excluded by `.gitignore`.
