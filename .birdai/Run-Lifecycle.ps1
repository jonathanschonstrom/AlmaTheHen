[CmdletBinding()]
param(
    [string]$Repo = 'C:\AlmaTheHen',
    [string]$Python = $env:BIRDAI_PYTHON,
    [string]$StateDirectory = '',
    [int]$Issue = 0,
    [switch]$Status,
    [switch]$OneStep,
    [string]$ApproveMerge = '',
    [string]$ApproveClose = '',
    [string]$AdoptSummary = '',
    [int]$AdoptPr = 0
)
$ErrorActionPreference = 'Stop'
$lifecycleConfigPath = Join-Path $PSScriptRoot 'runtime.json'
if (Test-Path -LiteralPath $lifecycleConfigPath) {
    $lifecycleConfig = Get-Content -LiteralPath $lifecycleConfigPath -Raw | ConvertFrom-Json
    if (-not $Python) { $Python = $lifecycleConfig.python }
    if (-not $StateDirectory) { $StateDirectory = $lifecycleConfig.state_directory }
}
if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }
$lifecycleArguments = @('-B', (Join-Path $PSScriptRoot 'e1_lifecycle.py'), '--repo', $Repo)
if ($StateDirectory) { $lifecycleArguments += @('--state-dir', $StateDirectory) }
if ($Issue) { $lifecycleArguments += @('--issue', [string]$Issue) }
if ($Status) { $lifecycleArguments += '--status' }
elseif (-not $OneStep) { $lifecycleArguments += '--until-gate' }
if ($ApproveMerge) { $lifecycleArguments += @('--approve-merge', $ApproveMerge) }
if ($ApproveClose) { $lifecycleArguments += @('--approve-close', $ApproveClose) }
if ($AdoptSummary) { $lifecycleArguments += @('--adopt-summary', $AdoptSummary) }
if ($AdoptPr) { $lifecycleArguments += @('--adopt-pr', [string]$AdoptPr) }
& $Python @lifecycleArguments
exit $LASTEXITCODE
