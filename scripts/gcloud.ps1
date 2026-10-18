# Workspace-scoped Google Cloud CLI. Credentials and tools are ignored by git.
[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$GcloudArgs)
$ErrorActionPreference = 'Stop'
$taskRepoRoot = Split-Path -Parent $PSScriptRoot
$taskCloudCli = Join-Path $taskRepoRoot '.tools\google-cloud-sdk\bin\gcloud.cmd'
if (-not (Test-Path -LiteralPath $taskCloudCli)) {
    throw 'Google Cloud CLI is not installed at .tools/google-cloud-sdk. See docs/cloud-auth.md.'
}
$env:CLOUDSDK_CONFIG = Join-Path $taskRepoRoot '.local\gcloud'
$taskPython = Join-Path $taskRepoRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $taskPython) { $env:CLOUDSDK_PYTHON = $taskPython }
& $taskCloudCli @GcloudArgs
exit $LASTEXITCODE
