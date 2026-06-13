param(
    [string]$ServiceUrl = "https://outlook-ai-spam-filter.onrender.com",
    [int]$MaxMessages = 500,
    [int]$PageSize = 25,
    [string]$BackupPath = ".\blocked-senders-backup.csv",
    [string]$Note = "Bulk reviewed Deleted Items"
)

$ErrorActionPreference = "Stop"

$envPath = Join-Path (Get-Location) ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Could not find .env in $(Get-Location). Run this script from the repo folder."
}

$adminToken = (
    Get-Content -LiteralPath $envPath |
        Where-Object { $_ -match "^ADMIN_TOKEN=" } |
        Select-Object -First 1
) -replace "^ADMIN_TOKEN=", ""

$adminToken = $adminToken.Trim().Trim('"').Trim("'")
if (-not $adminToken) {
    throw "ADMIN_TOKEN is missing from .env."
}

$headers = @{ "X-Admin-Token" = $adminToken }
$body = @{
    confirm_reviewed_deleted_items = $true
    max_messages = $MaxMessages
    page_size = $PageSize
    note = $Note
} | ConvertTo-Json

Write-Host "Blocking Deleted Items senders from up to $MaxMessages messages..."
$blockResult = Invoke-RestMethod `
    -Method Post `
    -Uri "$ServiceUrl/admin/deleted-senders/block-all" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body

Write-Host "Refreshing local backup at $BackupPath..."
Invoke-RestMethod `
    -Method Get `
    -Uri "$ServiceUrl/admin/blocked-senders" `
    -Headers $headers |
    Select-Object sender_email, created_at, source, note |
    Export-Csv -NoTypeInformation -Encoding UTF8 -Path $BackupPath

$blockedCount = $blockResult.blocked_count
$reviewedCount = $blockResult.reviewed_candidate_count
Write-Host "Done. Newly blocked: $blockedCount. Reviewed sender candidates: $reviewedCount."
Write-Host "Backup file: $((Resolve-Path -LiteralPath $BackupPath).Path)"
