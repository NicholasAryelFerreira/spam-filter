# Outlook AI Spam Filter

This project is a cloud-ready FastAPI app that watches your Outlook **Junk Email** folder, asks the OpenAI API to classify new junk mail, and then takes one of three actions:

- **Move to Inbox** only when the email is a verified provider login-code email, such as a legitimate OpenAI sign-in code.
- **Move to Deleted Items** when the email is clearly harmful spam, phishing, malware, extortion, credential theft, or a scam.
- **Leave in Junk Email** for everything else, including uncertain messages.

The default model is `gpt-5.4-nano`.

## What Is Already Built

Codex already implemented these project files:

- `spam_filter/app.py`: FastAPI web app, Microsoft Graph webhook endpoint, and admin endpoints.
- `spam_filter/graph.py`: Microsoft Graph authentication, message lookup, folder lookup, webhook subscription creation/renewal, and message moves.
- `spam_filter/classifier.py`: OpenAI structured-output classifier.
- `spam_filter/service.py`: spam-filter workflow and decision application.
- `spam_filter/database.py`: local SQLite storage for processed messages, decisions, webhook subscriptions, and manually blocked senders.
- `providers.json`: provider allowlist, starting with OpenAI.
- `Dockerfile`, `Procfile`, and `render.yaml`: cloud deployment helpers.
- `tests/`: local unit tests.

## What You Still Need To Do

You still need to:

1. Keep your real secrets in `.env` locally and in your cloud host environment variables.
2. Create a Microsoft Entra app registration.
3. Give that app Microsoft Graph delegated mail permissions.
4. Generate a Microsoft refresh token for your mailbox.
5. Deploy the app to a cloud host with a public HTTPS URL.
6. Create the Microsoft Graph webhook subscription.

Important: `.env` is ignored by git. Do not commit `.env`, refresh tokens, client secrets, or API keys.

## How The Optional Sender Blocking Works

The app includes an optional, manual review flow for senders found in **Deleted Items**.

This is **not** Outlook's native Blocked Senders list. It is an app-owned blocklist stored in SQLite. When you block a sender through this app, future messages from that exact email address are moved from Junk Email to Deleted Items automatically.

Blocking requires two steps:

1. You inspect sender candidates from Deleted Items.
2. You explicitly submit the senders you want to block.

Viewing candidates never blocks anything by itself.

## Local First-Time Installation

Use these steps on your PC to run the app locally for testing.

### 1. Open PowerShell

Open **PowerShell**.

### 2. Go To The Project Folder

Run this in **PowerShell**:

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
```

### 3. Confirm `.env` Is Ignored By Git

Run this in **PowerShell**:

```powershell
git check-ignore -v .env
```

Expected output should mention `.gitignore`.

### 4. Create The Virtual Environment

Run this in **PowerShell**:

```powershell
py -3.12 -m venv .venv
```

### 5. Activate The Virtual Environment

Run this in **PowerShell**:

```powershell
.\.venv\Scripts\Activate.ps1
```

Your prompt should start with `(.venv)`.

### 6. Install Python Dependencies

Run this in **PowerShell**:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 7. Verify Dependencies

Run this in **PowerShell**:

```powershell
python -c "import fastapi, httpx, openai, pydantic, uvicorn; print('dependencies ok')"
```

Expected output:

```text
dependencies ok
```

### 8. Run Tests

Run this in **PowerShell**:

```powershell
python -m unittest discover -s tests
```

Expected output should end with:

```text
OK
```

## Local `.env` Setup

Your `.env` file stays on your computer and should never be committed.

Use `.env.example` as a template.

Minimum local `.env` shape:

```text
OPENAI_API_KEY=<your OpenAI API key>
OPENAI_MODEL=gpt-5.4-nano

MS_TENANT_ID=common
MS_CLIENT_ID=<your Microsoft app client ID>
MS_CLIENT_SECRET=<your Microsoft app client secret>
MS_REFRESH_TOKEN=<your Microsoft refresh token>

GRAPH_NOTIFICATION_URL=https://your-cloud-host.example.com/webhooks/graph
GRAPH_CLIENT_STATE=<long random secret>
ADMIN_TOKEN=<long random admin token>
DATABASE_PATH=spam_filter.sqlite3
ENVIRONMENT=development
```

Notes:

- Localhost is useful for testing `/health`, `/admin/decisions`, and unit tests.
- Microsoft Graph webhooks require a public HTTPS URL. For real email automation, deploy to the cloud first.
- If you run locally only, Graph cannot call `http://127.0.0.1:8000/webhooks/graph` from the internet.

## Run The App Locally

### 1. Open PowerShell

Open **PowerShell**.

### 2. Go To The Project Folder

Run this in **PowerShell**:

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
```

### 3. Activate The Virtual Environment

Run this in **PowerShell**:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4. Start The App

Run this in **PowerShell**:

```powershell
uvicorn spam_filter.app:app --reload --host 127.0.0.1 --port 8000
```

### 5. Test Health

Open a second **PowerShell** window and run:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

## Microsoft Entra And Graph Setup

Microsoft setup has three parts:

1. Create the app registration.
2. Add Graph permissions.
3. Generate a refresh token for your mailbox.

Microsoft references:

- [Authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Microsoft Graph webhook delivery](https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks)
- [Create Graph subscription](https://learn.microsoft.com/en-us/graph/api/subscription-post-subscriptions?view=graph-rest-1.0)
- [Move message](https://learn.microsoft.com/en-us/graph/api/message-move?view=graph-rest-1.0)

### 1. Create The App Registration

Use your browser:

1. Open the **Microsoft Entra admin center**.
2. Go to **Identity**.
3. Go to **Applications**.
4. Go to **App registrations**.
5. Select **New registration**.
6. Name it:

```text
Outlook AI Spam Filter
```

7. For supported account types, choose the option that matches your mailbox. For a personal Microsoft account, choose the option that includes personal Microsoft accounts.
8. Add this redirect URI:

```text
http://localhost
```

9. Register the app.
10. Copy the **Application (client) ID** into `.env` as `MS_CLIENT_ID`.
11. Copy the **Directory (tenant) ID** into `.env` as `MS_TENANT_ID`, or use `common` if you intentionally want the common endpoint.

### 2. Create A Client Secret

Use your browser in the same app registration:

1. Open **Certificates & secrets**.
2. Select **New client secret**.
3. Add a description, such as:

```text
spam-filter-local-and-cloud
```

4. Choose an expiration.
5. Select **Add**.
6. Copy the secret **Value** immediately.
7. Save it in `.env` as `MS_CLIENT_SECRET`.

Important: copy the secret value, not the secret ID.

### 3. Add Microsoft Graph Permissions

Use your browser in the same app registration:

1. Open **API permissions**.
2. Select **Add a permission**.
3. Choose **Microsoft Graph**.
4. Choose **Delegated permissions**.
5. Add:

```text
Mail.ReadWrite
offline_access
```

6. Save the permissions.
7. If your tenant requires admin consent, select **Grant admin consent** or ask your admin to grant it.

Why these permissions:

- `Mail.ReadWrite` lets the app read Junk Email and move messages.
- `offline_access` lets the app use a refresh token so it can keep running in the cloud.

### 4. Generate A Refresh Token

This step signs in to your Microsoft mailbox once and exchanges the returned code for tokens.

Run these commands in **PowerShell**.

First go to the project folder:

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
```

Set your tenant and client ID in this PowerShell window:

```powershell
$tenant = "<your MS_TENANT_ID, or common>"
$clientId = "<your MS_CLIENT_ID>"
$redirectUri = "http://localhost"
$scope = "offline_access https://graph.microsoft.com/Mail.ReadWrite"
```

Build the sign-in URL:

```powershell
$encodedRedirect = [System.Web.HttpUtility]::UrlEncode($redirectUri)
$encodedScope = [System.Web.HttpUtility]::UrlEncode($scope)
$authUrl = "https://login.microsoftonline.com/$tenant/oauth2/v2.0/authorize?client_id=$clientId&response_type=code&redirect_uri=$encodedRedirect&response_mode=query&scope=$encodedScope&prompt=consent"
$authUrl
```

Copy the printed URL into your browser and sign in to the mailbox you want the app to protect.

After sign-in, the browser will redirect to a URL that starts with:

```text
http://localhost/?code=...
```

The page may fail to load. That is okay. Copy the full browser address.

Back in **PowerShell**, paste the full redirected URL here:

```powershell
$redirectedUrl = "<paste the full http://localhost/?code=... URL here>"
$code = [System.Web.HttpUtility]::ParseQueryString(([uri]$redirectedUrl).Query).Get("code")
```

Exchange the code for tokens:

```powershell
$clientSecret = "<your MS_CLIENT_SECRET>"
$tokenResponse = Invoke-RestMethod -Method Post -Uri "https://login.microsoftonline.com/$tenant/oauth2/v2.0/token" -ContentType "application/x-www-form-urlencoded" -Body @{
    client_id = $clientId
    client_secret = $clientSecret
    code = $code
    redirect_uri = $redirectUri
    grant_type = "authorization_code"
    scope = $scope
}
```

Confirm a refresh token was returned without printing it:

```powershell
[bool]$tokenResponse.refresh_token
```

Expected output:

```text
True
```

Save the refresh token into `.env` as `MS_REFRESH_TOKEN`.

Do not paste the refresh token into chat or commit it to git.

## Cloud Deployment On Render

Render is one practical option because this repo includes `render.yaml`.

### 1. Push The Repository To GitHub

This repo is configured with:

```text
https://github.com/NicholasAryelFerreira/spam-filter.git
```

`.env` is ignored and should not be pushed.

### 2. Create The Render Service

Use your browser:

1. Open Render.
2. Create a new **Blueprint** or **Web Service**.
3. Connect this GitHub repository.
4. If Render asks for a blueprint file, choose `render.yaml`.
5. Make sure the service has a persistent disk mounted at:

```text
/var/data
```

### 3. Add Render Environment Variables

In Render service settings, add:

```text
OPENAI_API_KEY=<your OpenAI API key>
OPENAI_MODEL=gpt-5.4-nano
ENVIRONMENT=production
DATABASE_PATH=/var/data/spam_filter.sqlite3
MS_TENANT_ID=<your Microsoft tenant ID, or common>
MS_CLIENT_ID=<your Microsoft app client ID>
MS_CLIENT_SECRET=<your Microsoft app client secret>
MS_REFRESH_TOKEN=<your Microsoft delegated refresh token>
GRAPH_NOTIFICATION_URL=https://your-render-service.onrender.com/webhooks/graph
GRAPH_CLIENT_STATE=<long random secret>
ADMIN_TOKEN=<long random admin token>
```

### 4. Deploy

Use the Render web dashboard to deploy the service.

After it deploys, copy the public service URL. It will look similar to:

```text
https://your-render-service.onrender.com
```

### 5. Test Cloud Health

Run this in **PowerShell** on your PC:

```powershell
Invoke-RestMethod -Method Get -Uri "https://your-render-service.onrender.com/health"
```

## Create And Renew The Microsoft Graph Subscription

Graph subscriptions are what make the app react when mail arrives. They expire, so you must renew them before expiration.

### Create The Subscription

Run this in **PowerShell**:

```powershell
Invoke-RestMethod -Method Post -Uri "https://your-render-service.onrender.com/admin/subscriptions" -Headers @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" }
```

### Renew The Subscription

Run this in **PowerShell**:

```powershell
Invoke-RestMethod -Method Post -Uri "https://your-render-service.onrender.com/admin/subscriptions/renew" -Headers @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" }
```

Renew before the `expires_at` date returned by `/health`.

## Admin Commands

All admin commands require:

```text
X-Admin-Token: <your ADMIN_TOKEN>
```

Replace `https://your-render-service.onrender.com` with your deployed URL.

### Review Recent Decisions

Run this in **PowerShell**:

```powershell
Invoke-RestMethod -Method Get -Uri "https://your-render-service.onrender.com/admin/decisions?limit=25" -Headers @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" }
```

### Manually Rescan Junk Email

Run this in **PowerShell**:

```powershell
Invoke-RestMethod -Method Post -Uri "https://your-render-service.onrender.com/admin/rescan-junk?top=25" -Headers @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" }
```

### Review Deleted Items Sender Candidates

This only lists candidates. It does not block anything.

Run this in **PowerShell**:

```powershell
Invoke-RestMethod -Method Get -Uri "https://your-render-service.onrender.com/admin/deleted-senders/candidates?top=50" -Headers @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" }
```

Look at the returned sender email addresses, message counts, and sample subjects. Decide which exact senders you want future Junk Email from to go straight to Deleted Items.

### Block Reviewed Senders

Only run this after reviewing the candidates.

Run this in **PowerShell**:

```powershell
Invoke-RestMethod -Method Post -Uri "https://your-render-service.onrender.com/admin/deleted-senders/block" -Headers @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" } -ContentType "application/json" -Body '{"senders":["spam@example.com"],"confirm_reviewed_deleted_items":true,"note":"Reviewed Deleted Items"}'
```

You can block more than one sender:

```powershell
Invoke-RestMethod -Method Post -Uri "https://your-render-service.onrender.com/admin/deleted-senders/block" -Headers @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" } -ContentType "application/json" -Body '{"senders":["spam1@example.com","spam2@example.com"],"confirm_reviewed_deleted_items":true,"note":"Reviewed Deleted Items"}'
```

### List Blocked Senders

Run this in **PowerShell**:

```powershell
Invoke-RestMethod -Method Get -Uri "https://your-render-service.onrender.com/admin/blocked-senders" -Headers @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" }
```

### Unblock A Sender

Run this in **PowerShell**:

```powershell
Invoke-RestMethod -Method Delete -Uri "https://your-render-service.onrender.com/admin/blocked-senders/spam@example.com" -Headers @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" }
```

## What Happens When A New Junk Email Arrives

1. Microsoft Graph sends a webhook notification to `/webhooks/graph`.
2. The app fetches the message.
3. The app ignores it if it is not currently in Junk Email.
4. If the sender is on the app blocklist, the app moves it to Deleted Items.
5. Otherwise, OpenAI classifies the message.
6. The app moves verified login codes to Inbox.
7. The app moves clearly harmful spam to Deleted Items.
8. The app leaves uncertain messages in Junk Email.
9. The app records the decision without storing the full email body.

## Troubleshooting

### `.env` Appears In `git status`

Run this in **PowerShell**:

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
git check-ignore -v .env
git status --short --ignored
```

`.env` should appear under ignored files as `!! .env`.

### Dependency Install Fails

Run this in **PowerShell**:

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt --no-cache-dir --timeout 120
```

### Tests Fail

Run this in **PowerShell**:

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests
```

Read the first failing test and fix that before deploying.

### The App Does Not Process Mail

Check these in order:

1. Cloud service is running.
2. `/health` works.
3. `GRAPH_NOTIFICATION_URL` matches your real cloud URL plus `/webhooks/graph`.
4. `ADMIN_TOKEN` in Render matches the token you use in PowerShell.
5. Microsoft Graph subscription exists in `/health`.
6. Microsoft refresh token is still valid.
7. The mailbox has new messages arriving in Junk Email.

## Security Checklist Before Every Commit

Run these in **PowerShell**:

```powershell
cd "C:\Users\nafer\github repo\Spam Filter"
git check-ignore -v .env
git status --short --ignored
```

Confirm:

- `.env` is ignored.
- `.venv` is ignored.
- `spam_filter.sqlite3` is ignored.
- No API keys, Microsoft client secrets, refresh tokens, or real tokens appear in tracked files.
