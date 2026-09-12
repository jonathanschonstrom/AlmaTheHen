#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9]+(-[a-z0-9]+)+$')][string]$SliceId,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Issue,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Goal,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$PassDefinition,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string[]]$AllowedFiles,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$ValidationCommand,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$OutputPath,
    [ValidateRange(1, 86400)][int]$TimeoutSeconds = 20,
    [string]$TimeoutReason = ''
)
$ErrorActionPreference = 'Stop'
foreach ($value in @($Issue, $Goal, $PassDefinition, $ValidationCommand)) {
    if ([string]::IsNullOrWhiteSpace($value)) { throw 'Task fields must not be blank.' }
}
if ($TimeoutSeconds -gt 20 -and [string]::IsNullOrWhiteSpace($TimeoutReason)) {
    throw 'A timeout above 20 seconds requires a task-local TimeoutReason.'
}
foreach ($file in $AllowedFiles) {
    if ([string]::IsNullOrWhiteSpace($file) -or $file -match '[\\:*?\[\]]' -or
        $file.StartsWith('/') -or ($file.Split('/') | Where-Object { $_ -in @('', '.', '..') })) {
        throw "Use exact repository-relative forward-slash file paths: $file"
    }
}
$task = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'execution-slice.template.json') | ConvertFrom-Json
$task.goal.slice_id = $SliceId
$task.goal.issue = $Issue
$task.goal.objective = $Goal
$task.goal.pass_definition = $PassDefinition
$task.allowed_files = @($AllowedFiles | Select-Object -Unique)
$task.validation.command = $ValidationCommand
$task.validation.timeout_seconds = $TimeoutSeconds
$task.validation.timeout_reason = $TimeoutReason
$json = $task | ConvertTo-Json -Depth 10
$destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
[System.IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
# Atomic refusal to replace an active task, including concurrent creation.
$stream = [System.IO.File]::Open($destination, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
try {
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($json + "`n")
    $stream.Write($bytes, 0, $bytes.Length)
} finally {
    $stream.Dispose()
}
Write-Output $destination
