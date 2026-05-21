<#
.SYNOPSIS
    GCP project + service-account provisioning. Run AFTER you have manually
    created the GCP project in the Console (see docs/runbooks/phase0-provisioning.md).

.PARAMETER ProjectId
    GCP project ID (e.g. fan360-labs-ak).

.PARAMETER Region
    GCP region (default europe-west1).

.PARAMETER EnableBilling
    Pass -EnableBilling to also enable services that require billing
    (Cloud Run, Firestore, Cloud Scheduler). Defaults off; enable at Phase 2 per phase2-live-feed runbook.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ProjectId,
    [string] $Region = 'europe-west1',
    [switch] $EnableBilling
)

$ErrorActionPreference = 'Stop'

Write-Host "`nSwitching gcloud to project $ProjectId" -ForegroundColor Cyan
gcloud config set project $ProjectId | Out-Null
gcloud config set compute/region $Region | Out-Null

Write-Host "`nEnabling no-billing APIs..." -ForegroundColor Cyan
$noBillingApis = @(
    'bigquery.googleapis.com',
    'storage-api.googleapis.com',
    'cloudbuild.googleapis.com',
    'secretmanager.googleapis.com',
    'generativelanguage.googleapis.com'
)
foreach ($api in $noBillingApis) {
    Write-Host "  enable: $api"
    gcloud services enable $api | Out-Null
}

if ($EnableBilling) {
    Write-Host "`nEnabling billing-required APIs (Phase 2+)..." -ForegroundColor Yellow
    $billingApis = @(
        'run.googleapis.com',
        'firestore.googleapis.com',
        'cloudscheduler.googleapis.com',
        'pubsub.googleapis.com',
        'aiplatform.googleapis.com'
    )
    foreach ($api in $billingApis) {
        Write-Host "  enable: $api"
        gcloud services enable $api | Out-Null
    }
}

Write-Host "`nCreating service accounts..." -ForegroundColor Cyan
$accounts = @(
    @{ Name = 's7-etl';          Display = 'Scenario 7 ETL';        Roles = @('roles/bigquery.dataEditor','roles/bigquery.jobUser','roles/storage.objectAdmin') },
    @{ Name = 's7-shim';         Display = 'Scenario 7 LLM Shim';   Roles = @('roles/secretmanager.secretAccessor') },
    @{ Name = 's7-live-ingest';  Display = 'Scenario 7 Live Ingest'; Roles = @('roles/bigquery.dataEditor','roles/bigquery.jobUser','roles/secretmanager.secretAccessor') }
)

foreach ($a in $accounts) {
    $sa = "$($a.Name)@$ProjectId.iam.gserviceaccount.com"
    Write-Host "  create: $sa"
    gcloud iam service-accounts create $a.Name --display-name="$($a.Display)" 2>$null
    foreach ($role in $a.Roles) {
        Write-Host "    bind:  $role"
        gcloud projects add-iam-policy-binding $ProjectId `
            --member="serviceAccount:$sa" `
            --role=$role `
            --condition=None `
            --quiet | Out-Null
    }
}

Write-Host "`nIssuing ETL service-account key to .secrets\s7-etl.json" -ForegroundColor Cyan
$keyPath = Join-Path $PSScriptRoot '..\.secrets\s7-etl.json'
if (Test-Path $keyPath) {
    Write-Host "  key file exists, skipping. Rotate with 'gcloud iam service-accounts keys delete' if needed."
} else {
    gcloud iam service-accounts keys create $keyPath `
        --iam-account="s7-etl@$ProjectId.iam.gserviceaccount.com" | Out-Null
    Write-Host "  wrote $keyPath"
}

Write-Host "`nDone. Next: open docs/runbooks/phase0-provisioning.md step 3." -ForegroundColor Green
