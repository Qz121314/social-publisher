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

## Development milestones

1. Project skeleton and local web admin
2. iXBrowser Local API connectivity and profile sync
3. Selenium attach/open/close lifecycle
4. Profile locking and worker execution model
5. Facebook single-account publishing proof of concept
6. Media publishing and verification
7. Scheduled jobs and multi-account worker pool
8. Batch scheduling and execution history
9. Additional platform adapters

## Local API

iXBrowser Local API defaults to:

```text
http://127.0.0.1:53200/api/v2/
```

The application must never commit social-account passwords, cookies, API tokens, or other secrets to Git.
