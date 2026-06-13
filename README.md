# Outlook AI Spam Filter

A cloud-ready FastAPI service that monitors Outlook Junk Email with Microsoft Graph, classifies messages with the OpenAI API, and moves mail according to a conservative spam-filter policy.

## Features

- Watches Outlook mail through Microsoft Graph webhooks.
- Processes only messages currently in Junk Email.
- Moves verified provider login-code emails, such as legitimate OpenAI sign-in codes, to Inbox.
- Moves clearly harmful spam to Deleted Items.
- Leaves uncertain or ordinary messages in Junk Email.
- Supports an optional app-owned blocked-sender list based on manual review of Deleted Items.
- Stores decisions in SQLite without storing full email bodies.

## Stack

- Python 3.12
- FastAPI
- Microsoft Graph
- OpenAI Responses API
- SQLite
- Docker / Render-ready deployment files

## Quick Start

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s tests
uvicorn spam_filter.app:app --reload --host 127.0.0.1 --port 8000
```

## Configuration

Copy `.env.example` to `.env` for local development and set the required values:

```text
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-nano
MS_TENANT_ID=common
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_REFRESH_TOKEN=
GRAPH_NOTIFICATION_URL=
GRAPH_CLIENT_STATE=
ADMIN_TOKEN=
DATABASE_PATH=spam_filter.sqlite3
```

Do not commit `.env`. The repository ignores `.env`, local virtual environments, SQLite runtime databases, and Python caches.

## Admin Endpoints

Admin endpoints require the `X-Admin-Token` header when `ADMIN_TOKEN` is configured.

- `GET /health`
- `POST /admin/subscriptions`
- `POST /admin/subscriptions/renew`
- `POST /admin/rescan-junk`
- `GET /admin/decisions`
- `GET /admin/deleted-senders/candidates`
- `POST /admin/deleted-senders/block`
- `GET /admin/blocked-senders`
- `DELETE /admin/blocked-senders/{sender_email}`

## Deployment

The project includes `Dockerfile`, `Procfile`, and `render.yaml`. Deploy to a host with a public HTTPS URL, set `GRAPH_NOTIFICATION_URL` to:

```text
https://your-service.example.com/webhooks/graph
```

The Microsoft app registration needs delegated Graph permissions for `User.Read`, `Mail.ReadWrite`, and `offline_access`.

Then create the Microsoft Graph subscription:

```powershell
Invoke-RestMethod -Method Post -Uri "https://your-service.example.com/admin/subscriptions" -Headers @{ "X-Admin-Token" = "<admin token>" }
```

Graph subscriptions expire and must be renewed:

```powershell
Invoke-RestMethod -Method Post -Uri "https://your-service.example.com/admin/subscriptions/renew" -Headers @{ "X-Admin-Token" = "<admin token>" }
```

## Tests

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests
```
