# Google Cloud authentication

Project selected by the user: `work-511514`. Authentication does not authorize resource creation or changes to billing/IAM.

The local Google Cloud SDK is under `.tools/google-cloud-sdk`; its configuration and credentials are under `.local/gcloud`. Both directories are ignored by git. Never copy them into containers, committed files, CI artifacts or chat. CI will use Workload Identity Federation; deployed services use workload identities rather than developer credentials.

Windows wrapper (from repository root):

```powershell
.\scripts\gcloud.ps1 auth login --project=work-511514
.\scripts\gcloud.ps1 auth application-default login
.\scripts\gcloud.ps1 auth application-default set-quota-project work-511514
.\scripts\gcloud.ps1 projects describe work-511514 --format='value(projectId,lifecycleState)'
```

The first browser sign-in authenticates deployment/administration CLI commands; Application Default Credentials separately authenticates local Python Google clients. Complete Google's account/consent UI yourself; no credential or code needs to be pasted into chat. The quota project configuration requires appropriate Service Usage permission; a failure must be reported, not bypassed with a key.

Before using Python clients in this workspace:

```powershell
$env:CLOUDSDK_CONFIG = Join-Path (Get-Location) '.local\gcloud'
$env:GOOGLE_CLOUD_PROJECT = 'work-511514'
```

Do not run `print-access-token` into logs or read credential files to report their contents. Verify authentication through read-only project/API checks. Confirm spend limits, storage region, environment separation and exact infrastructure plan before provisioning. A successful account sign-in alone does not prove model access, billing readiness, quotas or region support.

Sign out of this workspace when needed:

```powershell
.\scripts\gcloud.ps1 auth revoke
.\scripts\gcloud.ps1 auth application-default revoke
```
