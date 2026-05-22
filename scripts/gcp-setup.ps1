<#
.SYNOPSIS
    GCP project + service-account provisioning. Run AFTER you have manually
    created the GCP project in the Console (see docs/runbooks/phase0-provisioning.md).

.PARAMETER ProjectId
    GCP project ID (e.g. sf-fan360).

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

function Invoke-GcloudQuiet {
    param([Parameter(Mandatory)][string[]] $GcloudArgv)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $out = & gcloud @GcloudArgv 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    return @{ ExitCode = $code; Output = ($out | Out-String).Trim() }
}

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
    @{ Name = 'etl-service';   Display = 'Fan 360 ETL';        Roles = @('roles/bigquery.dataEditor', 'roles/bigquery.jobUser', 'roles/storage.objectAdmin', 'roles/storage.bucketViewer') },
    @{ Name = 'llm-shim';      Display = 'Fan 360 LLM Shim';   Roles = @('roles/secretmanager.secretAccessor') },
    @{ Name = 'live-ingest';   Display = 'Fan 360 Live Ingest'; Roles = @('roles/bigquery.dataEditor', 'roles/bigquery.jobUser', 'roles/secretmanager.secretAccessor', 'roles/cloudscheduler.admin') }

)

foreach ($a in $accounts) {
    $sa = "$($a.Name)@$ProjectId.iam.gserviceaccount.com"
    $desc = Invoke-GcloudQuiet -GcloudArgv @('iam', 'service-accounts', 'describe', $sa, '--format=value(email)')
    if ($desc.ExitCode -eq 0) {
        Write-Host "  exists:  $sa"
    } else {
        Write-Host "  create:  $sa"
        $create = Invoke-GcloudQuiet -GcloudArgv @(
            'iam', 'service-accounts', 'create', $a.Name,
            '--display-name', $a.Display
        )
        if ($create.ExitCode -ne 0 -and $create.Output -notmatch 'already exists') {
            throw "Failed to create $sa`: $($create.Output)"
        }
    }

    foreach ($role in $a.Roles) {
        Write-Host "    bind:  $role"
        gcloud projects add-iam-policy-binding $ProjectId `
            --member="serviceAccount:$sa" `
            --role=$role `
            --condition=None `
            --quiet | Out-Null
    }
}

Write-Host "`nIssuing ETL service-account key to .secrets\etl-service.json" -ForegroundColor Cyan
$keyPath = Join-Path $PSScriptRoot '..\.secrets\etl-service.json'

if (Test-Path $keyPath) {
    Write-Host "  key file exists, skipping. Rotate with 'gcloud iam service-accounts keys delete' if needed."
} else {
    $key = Invoke-GcloudQuiet -GcloudArgv @(
        'iam', 'service-accounts', 'keys', 'create', $keyPath,
        '--iam-account', "etl-service@$ProjectId.iam.gserviceaccount.com"
    )
    if ($key.ExitCode -ne 0) {
        throw "Failed to create key at $keyPath`: $($key.Output)"
    }
    Write-Host "  wrote $keyPath"
}

Write-Host "`nDone. Service accounts: etl-service, llm-shim, live-ingest (@$ProjectId)." -ForegroundColor Green
Write-Host "Next: docs/runbooks/phase2-live-feed.md (billing on) or phase0 step 3 if keys only." -ForegroundColor Green
