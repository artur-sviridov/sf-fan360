<#
.SYNOPSIS
    One-shot local bootstrap for the Fan 360 Labs second-screen project.

.DESCRIPTION
    Creates the Python venv, installs the ETL package in editable mode,
    installs Node devDependencies, and verifies tool versions.

    Does NOT perform any cloud action - that lives in scripts/gcp-setup.ps1
    and the Phase 0 runbook.
#>

[CmdletBinding()]
param(
    [switch] $SkipNode
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\..

function Test-Tool {
    param([string] $Name, [string] $VersionArg = '--version', [string] $MinHint = '')
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "[MISSING] $Name $MinHint" -ForegroundColor Yellow
        return $false
    }
    $v = & $Name $VersionArg.Split(' ') 2>&1 | Select-Object -First 1
    Write-Host "[OK]      $Name -> $v"
    return $true
}

Write-Host "`n=== Tool versions ===" -ForegroundColor Cyan
$pyOk = Test-Tool 'python' '--version' '(need >= 3.11)'
$gitOk = Test-Tool 'git' '--version'
$sfOk = Test-Tool 'sf' '--version' '(Salesforce CLI)'
$nodeOk = if ($SkipNode) { $true } else { Test-Tool 'node' '--version' '(need >= 22)' }
$gcloudOk = Test-Tool 'gcloud' '--version' '(install from https://cloud.google.com/sdk/docs/install)'

if (-not $pyOk -or -not $gitOk -or -not $sfOk) {
    Write-Host "`nPlease install the missing prerequisites and rerun." -ForegroundColor Red
    exit 1
}

if (-not $gcloudOk) {
    Write-Host "`ngcloud is required for Phases 1+. Install before continuing." -ForegroundColor Yellow
}

Write-Host "`n=== Python venv ===" -ForegroundColor Cyan
if (-not (Test-Path .venv)) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -e ".[dev]"

Write-Host "`n=== Verifying Python imports ===" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -c "import understatapi, google.cloud.bigquery; print('python deps ok')"

if (-not $SkipNode) {
    Write-Host "`n=== Node devDependencies ===" -ForegroundColor Cyan
    npm install
}

Write-Host "`n=== .env ===" -ForegroundColor Cyan
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from template. Edit it to add your API keys."
} else {
    Write-Host ".env already exists. Skipping."
}

Write-Host "`nBootstrap complete." -ForegroundColor Green
Write-Host "Next: read docs/runbooks/phase0-provisioning.md and complete the human-only steps."
