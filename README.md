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
- **Scheduling:** APScheduler layer planned after platform publishing is proven locally

## Current capabilities

- iXBrowser profile sync and local cache
- Selenium open / attach / probe / close lifecycle
- Exclusive profile locks and a 3-worker execution pool
- Restart recovery for stale locks and interrupted tasks
- Content drafts with text, images, videos, or mixed image/video media
- Multi-select iX target profiles; UI sequence numbers are display-only and the database stores the stable iX `profile_id`
- One `publish_job` per selected iX profile
- Local media storage under `data/uploads/`
- Facebook desktop-web adapter with login/checkpoint detection
- Facebook composer open, text entry, image/video file upload, media-processing wait, Post submission and post-submission verification
- Conservative `needs_review` state when submission may have happened but verification is ambiguous
- Immediate **Publish now** action for all runnable target jobs in a content item
- Per-profile publish state in the Web admin
- GitHub Actions checks for backend compile/import and frontend build

The publishing UI does **not** require selecting a Facebook account and an iX profile separately. The execution identity is the selected iX profile. Login sessions stay inside iXBrowser.

## Publish safety model

Publish jobs use these relevant states:

```text
draft
queued
running
succeeded
failed
needs_review
```

`needs_review` is intentionally different from `failed`. It is used when:

- Facebook requires login/checkpoint/manual account review, or
- the Post button may already have been submitted but the new post could not be independently verified.

A `needs_review` job is **not automatically retried**, because doing so could create a duplicate Facebook post.

If the backend restarts while a publish job is already `running`, the job is also moved to `needs_review` instead of being replayed automatically.

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

A single content item can target many iX profiles. Each selected profile receives its own `publish_jobs` row so scheduling, locking, verification and history happen independently.

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

The generic content model allows ordered image and video assets together. Platform adapters remain responsible for validating platform-specific publishing behavior.

## Local development

Start iXBrowser first and enable its Local API. Default endpoint:

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

## First Facebook publish test

Use an iX profile containing a Facebook account you are authorized to manage.

1. Start iXBrowser and enable Local API.
2. Start backend and frontend.
3. Click **Sync iX Profiles**.
4. Optionally use **Open** / **Check** to confirm Selenium attaches correctly.
5. If needed, log in to Facebook manually inside that iX profile and close it normally.
6. In **Create publish draft**, choose Facebook.
7. Select one iX profile for the first test.
8. Enter a short unique text and attach a small image and/or short video.
9. Create the draft.
10. Click **Publish now**.
11. Watch the target job move through `queued` -> `running` -> `succeeded`, `failed`, or `needs_review`.

For the very first DOM calibration, use only one profile and non-critical test content. Facebook changes its desktop DOM frequently, so selectors may require local adjustment even when CI passes.

## Worker execution path

```text
PublishJob
  -> WorkerTask
  -> acquire profile lock
  -> open iX profile
  -> attach Selenium
  -> Facebook login/checkpoint check
  -> open composer
  -> enter text
  -> upload image/video media
  -> wait for media processing
  -> click Post
  -> verify success/feed evidence
  -> update PublishJob
  -> close profile when worker opened it
  -> release profile lock
```

If the composer closes after Post but verification cannot locate the new post, the job becomes `needs_review`, not `failed`.

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
POST   /api/contents/{content_id}/run
DELETE /api/contents/{content_id}
GET    /api/media/{media_id}/file

GET    /api/publish-jobs
POST   /api/publish-jobs/{job_id}/run

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
7. Facebook Selenium publish execution PoC — code complete, local DOM calibration pending
8. Scheduler and scheduled job dispatch
9. Batch/staggered multi-profile publishing and retry policy
10. Additional platform adapters

## Security and scope

Use this system only for profiles/accounts you are authorized to manage. The project does not attempt to bypass Facebook security challenges, CAPTCHA, checkpoints, account recovery or other platform controls. Those states require manual review.

Never commit passwords, cookies, API tokens, proxy credentials, or other secrets to Git. Runtime database files, uploaded media and `.env` files are excluded by `.gitignore`.
