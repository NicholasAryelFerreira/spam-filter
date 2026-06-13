param(
    [string]$ServiceUrl = "https://outlook-ai-spam-filter.onrender.com",
    [string]$BackupPath = ".\blocked-senders-backup.csv",
    [int]$ChunkSize = 100,
    [string]$Note = "Restored from local CSV backup"
)

$ErrorActionPreference = "Stop"

$envPath = Join-Path (Get-Location) ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Could not find .env in $(Get-Location). Run this script from the repo folder."
}

if (-not (Test-Path -LiteralPath $BackupPath)) {
    throw "Could not find backup CSV at $BackupPath."
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

$senders = Import-Csv -LiteralPath $BackupPath |
    ForEach-Object { $_.sender_email } |
    Where-Object { $_ } |
    ForEach-Object { $_.Trim().ToLowerInvariant() } |
    Sort-Object -Unique

if (-not $senders) {
    throw "No sender_email values found in $BackupPath."
}

$headers = @{ "X-Admin-Token" = $adminToken }
$restored = 0

for ($index = 0; $index -lt $senders.Count; $index += $ChunkSize) {
    $end = [Math]::Min($index + $ChunkSize - 1, $senders.Count - 1)
    $chunk = @($senders[$index..$end])
    $body = @{
        confirm_reviewed_deleted_items = $true
        senders = $chunk
        note = $Note
    } | ConvertTo-Json

    Invoke-RestMethod `
        -Method Post `
        -Uri "$ServiceUrl/admin/deleted-senders/block" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $body |
        Out-Null

    $restored += $chunk.Count
    Write-Host "Restored $restored of $($senders.Count) senders..."
}

Write-Host "Done. Restored $restored app-blocked senders from $BackupPath."
