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
OPENAI_CLASSIFICATION_PROMPT=
MS_TENANT_ID=common
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_REFRESH_TOKEN=
GRAPH_NOTIFICATION_URL=
GRAPH_CLIENT_STATE=
ADMIN_TOKEN=
DATABASE_PATH=spam_filter.sqlite3
INBOX_CONFIDENCE_THRESHOLD=0.92
DELETE_CONFIDENCE_THRESHOLD=0.88
```

Do not commit `.env`. The repository ignores `.env`, local virtual environments, SQLite runtime databases, and Python caches.

`OPENAI_CLASSIFICATION_PROMPT` controls the model's classification instructions. Keep the structured-output labels intact: `legit_login_code`, `junk_keep`, `spam_harmful`, `move_to_inbox`, `keep_in_junk`, and `move_to_deleted`.

Local `.env` and Render environment variables are separate:

- Local `.env` controls the app only when you run it on your own computer.
- Render environment variables control the deployed cloud app.
- Changing local `.env` does not change Render.
- Changing Render does not change local `.env`.
- To change live cloud behavior, update the variable in Render and redeploy.
- To keep local testing consistent with Render, update the same variable in `.env` too.

Threshold variables are optional because the app has defaults:

- `INBOX_CONFIDENCE_THRESHOLD` defaults to `0.92`.
- `DELETE_CONFIDENCE_THRESHOLD` defaults to `0.88`.

If these variables are missing in Render, the deployed app still uses those defaults. Add them in Render only if you want to change the live thresholds.

## Admin Endpoints

Admin endpoints require the `X-Admin-Token` header when `ADMIN_TOKEN` is configured.

- `GET /health`
- `GET /admin/diagnostics`
- `POST /admin/subscriptions`
- `POST /admin/subscriptions/ensure`
- `POST /admin/subscriptions/renew`
- `POST /admin/rescan-junk`
- `POST /admin/rescan-junk-all`
- `GET /admin/decisions`
- `GET /admin/deleted-senders/candidates`
- `GET /admin/deleted-senders/candidates-all`
- `POST /admin/deleted-senders/block`
- `POST /admin/deleted-senders/block-all`
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

Use `POST /admin/subscriptions/ensure` for automation. It creates a subscription when none is recorded and renews existing subscriptions when they are present.

## Operations

Set local PowerShell variables before running admin commands:

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
$serviceUrl = "https://outlook-ai-spam-filter.onrender.com"
$adminToken = ((Get-Content .env | Where-Object { $_ -match '^ADMIN_TOKEN=' }) -replace '^ADMIN_TOKEN=', '').Trim()
```

Check service health:

```powershell
Invoke-RestMethod -Method Get -Uri "$serviceUrl/health" | ConvertTo-Json -Depth 5
```

Check configuration and Microsoft Graph access:

```powershell
Invoke-RestMethod -Method Get -Uri "$serviceUrl/admin/diagnostics" -Headers @{ "X-Admin-Token" = $adminToken } | ConvertTo-Json -Depth 5
```

Create or renew the Graph subscription:

```powershell
Invoke-RestMethod -Method Post -Uri "$serviceUrl/admin/subscriptions/ensure" -Headers @{ "X-Admin-Token" = $adminToken } | ConvertTo-Json -Depth 5
```

Process recent Junk Email manually:

```powershell
Invoke-RestMethod -Method Post -Uri "$serviceUrl/admin/rescan-junk?top=25" -Headers @{ "X-Admin-Token" = $adminToken } | ConvertTo-Json -Depth 6
```

Process older Junk Email in batches:

```powershell
Invoke-RestMethod -Method Post -Uri "$serviceUrl/admin/rescan-junk-all?max_messages=500&page_size=25" -Headers @{ "X-Admin-Token" = $adminToken } | ConvertTo-Json -Depth 6
```

Use this carefully because each unprocessed message may call the OpenAI API. On free Render, large scans can be slow or time out. Start with `max_messages=50`, then increase if needed.

Before scanning all Junk Email:

1. Make sure Render has redeployed the latest commit.
2. Copy any local `.env` prompt changes to Render's `OPENAI_CLASSIFICATION_PROMPT` environment variable.
3. Run `/admin/diagnostics` and confirm Graph auth is `ok`.
4. Run `/admin/rescan-junk?top=5` first.
5. Review `/admin/decisions`.
6. If the first results look right, run `/admin/rescan-junk-all?max_messages=50&page_size=25`.
7. Increase `max_messages` gradually.

Review recent decisions:

```powershell
Invoke-RestMethod -Method Get -Uri "$serviceUrl/admin/decisions?limit=25" -Headers @{ "X-Admin-Token" = $adminToken } | ConvertTo-Json -Depth 6
```

Review Deleted Items sender candidates:

```powershell
Invoke-RestMethod -Method Get -Uri "$serviceUrl/admin/deleted-senders/candidates?top=50" -Headers @{ "X-Admin-Token" = $adminToken } | ConvertTo-Json -Depth 6
```

Review sender candidates from more of the actual Outlook Deleted Items folder:

```powershell
Invoke-RestMethod -Method Get -Uri "$serviceUrl/admin/deleted-senders/candidates-all?max_messages=500&page_size=25" -Headers @{ "X-Admin-Token" = $adminToken } | ConvertTo-Json -Depth 6
```

Block all unique senders found in the actual Outlook Deleted Items folder scan:

```powershell
Invoke-RestMethod -Method Post -Uri "$serviceUrl/admin/deleted-senders/block-all" -Headers @{ "X-Admin-Token" = $adminToken } -ContentType "application/json" -Body '{"confirm_reviewed_deleted_items":true,"max_messages":500,"page_size":25,"note":"Bulk reviewed Deleted Items"}'
```

List app-blocked senders:

```powershell
Invoke-RestMethod -Method Get -Uri "$serviceUrl/admin/blocked-senders" -Headers @{ "X-Admin-Token" = $adminToken } | ConvertTo-Json -Depth 5
```

Unblock one sender:

```powershell
Invoke-RestMethod -Method Delete -Uri "$serviceUrl/admin/blocked-senders/spam@example.com" -Headers @{ "X-Admin-Token" = $adminToken }
```

The bulk Deleted Items block scans Outlook's real Deleted Items folder, including messages the app moved there and messages you manually moved or deleted there. It blocks unique sender email addresses found in that scan, up to `max_messages`.

Blocked senders are stored in this app's SQLite database. They are not written to Outlook's native "Blocked senders and domains" list. When a blocked sender later appears in Junk Email, this app moves that message to Deleted Items.

On Render Free, the app's SQLite database can be lost on restart or redeploy because there is no persistent disk. For durable app-blocked senders and decision history, use a persistent disk or external database.

## Subscription Automation

Microsoft Graph Outlook message subscriptions cannot last forever. The maximum lifetime for Outlook message subscriptions is under seven days, so the app must renew or recreate the subscription regularly.

This repo includes a GitHub Actions workflow at `.github/workflows/ensure-graph-subscription.yml`. It runs daily and calls:

```text
POST /admin/subscriptions/ensure
```

This workflow renews or recreates the Microsoft Graph webhook subscription. It does not rotate the Microsoft refresh token. If the Microsoft refresh token is revoked, expires, or is invalidated by account/security changes, generate a new `MS_REFRESH_TOKEN` and update it in Render.

To enable it, add these GitHub repository secrets:

```text
SPAM_FILTER_SERVICE_URL=https://outlook-ai-spam-filter.onrender.com
SPAM_FILTER_ADMIN_TOKEN=<your ADMIN_TOKEN>
```

In GitHub:

1. Open the repository.
2. Go to **Settings**.
3. Go to **Secrets and variables**.
4. Click **Actions**.
5. Click **New repository secret**.
6. Add `SPAM_FILTER_SERVICE_URL`.
7. Add `SPAM_FILTER_ADMIN_TOKEN`.
8. Go to **Actions**.
9. Select **Ensure Microsoft Graph subscription**.
10. Click **Run workflow** once to test it.

GitHub Actions is also the default failure notification path. If the Render service is down, the admin token is wrong, Microsoft Graph auth fails, the refresh token stops working, or the subscription cannot be renewed, the workflow should fail.

To receive failure notifications:

1. Open GitHub.
2. Click your profile picture in the top-right corner.
3. Click **Settings**.
4. Click **Notifications**.
5. Find the **Actions** notification settings.
6. Enable email or web notifications for failed workflow runs.
7. Open this repository.
8. Go to **Actions**.
9. Open **Ensure Microsoft Graph subscription**.
10. Confirm the latest run is green.

This does not send a separate text message or custom email from the app itself. It relies on GitHub's workflow-failure notifications.

## Tests

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests
```
