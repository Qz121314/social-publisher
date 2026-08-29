# Social Publisher

Local-first multi-account social publishing system built around iXBrowser profiles.

## Architecture

- **Frontend:** React + TypeScript + Vite
- **Backend:** Python 3.12 + FastAPI
- **Database:** SQLite + SQLAlchemy
- **Browser:** iXBrowser Local API + Selenium 4
- **Execution:** bounded worker pool + database-backed profile locks
- **Content:** local text/image/video library + per-profile publish jobs
- **Platform layer:** independent adapters, starting with Facebook
- **Scheduling:** APScheduler layer planned after platform publishing is proven

## Current capabilities

- iXBrowser profile sync and local cache
- Selenium open / attach / probe / close lifecycle
- Exclusive profile locks and a 3-worker execution pool
- Restart recovery for stale locks and interrupted worker tasks
- Generic platform account metadata
- Content drafts with text, images, videos, or mixed image/video media
- Multi-select iX target profiles; the UI shows a friendly sequence number but the database stores the stable iX `profile_id`
- One `publish_job` created per selected profile
- Local media storage under `data/uploads/`
- Facebook adapter contract with image/video capability validation and login-state inspection foundation
- React content composer and recent draft library
- GitHub Actions checks for backend import and frontend build

The publishing UI does **not** require selecting a Facebook account and an iX profile separately. The target identity for execution is the iX profile. The `accounts` table remains internal metadata for platform/account state.

## Database

Runtime database:

```text
data/social_publisher.db
```

Main tables:

```text
browser_profiles
accounts
contents
media_assets
publish_jobs
profile_locks
worker_tasks
```

A single content item can target many iX profiles. Each selected profile receives its own `publish_jobs` row so scheduling, locking, retries, verification and history can later happen independently.

## Media

Uploads are stored locally in:

```text
data/uploads/
```

Accepted media categories are currently:

```text
image/*
video/*
```

The generic content model allows ordered image and video assets together. Individual platform adapters remain responsible for validating what a platform can actually publish.

## Local development

Start iXBrowser first and enable its Local API. The default endpoint is:

```text
http://127.0.0.1:53200/api/v2/
```

Backend:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

Frontend in another PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

FastAPI docs:

```text
http://127.0.0.1:8765/docs
```

## Content workflow

1. Sync iX profiles.
2. Open **Create publish draft**.
3. Choose the platform (Facebook is currently registered).
4. Select one or many iX profiles. Display numbers such as `001`, `002` are UI-only; the saved target is the real iX `profile_id`.
5. Enter text and/or add image/video files.
6. Create the draft.
7. The backend stores media and creates one draft publish job per selected profile.

No social password, cookie or login token is stored by Social Publisher. Login sessions remain inside the iXBrowser profile.

## Browser / worker workflow

Diagnostic worker execution currently follows:

```text
queued
  -> running
  -> acquire profile lock
  -> open iX profile
  -> attach Selenium
  -> inspect browser
  -> close when appropriate
  -> release profile lock
  -> succeeded / failed / blocked
```

Manual Open / Check / Close operations are rejected while a Worker owns that profile lock.

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

GET    /api/platforms
GET    /api/contents
GET    /api/contents/{content_id}
POST   /api/contents
DELETE /api/contents/{content_id}
GET    /api/media/{media_id}/file

GET    /api/profile-locks
POST   /api/profile-locks/cleanup
GET    /api/worker/tasks
GET    /api/worker/tasks/{task_id}
POST   /api/worker/test/{profile_id}

GET    /api/accounts
POST   /api/accounts
PATCH  /api/accounts/{account_id}
DELETE /api/accounts/{account_id}
```

## Milestones

1. Project skeleton and local web admin — done
2. iXBrowser Local API connectivity and profile sync — done
3. SQLite and account management — done
4. Selenium attach/open/close lifecycle — done
5. Profile locking and worker execution model — done
6. Content + image/video media + per-profile publish-job model — done
7. Facebook Selenium publishing: text + image/video upload + publish verification — next
8. Scheduler and scheduled job dispatch
9. Batch/staggered multi-profile publishing and retry policy
10. Additional platform adapters

## Security

Use this system only for profiles/accounts you are authorized to manage. Never commit passwords, cookies, API tokens, proxy credentials, or other secrets to Git. Runtime database files, uploaded media and `.env` files are excluded by `.gitignore`.
