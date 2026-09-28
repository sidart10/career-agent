$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pointer = Join-Path $root '.career-agent/active-runtime'
if (!(Test-Path $pointer)) { Write-Error 'Run ./scripts/install.ps1 first.'; exit 3 }
$relative = (Get-Content $pointer -Raw).Trim()
if ($relative -notmatch '^runtimes/[0-9a-f]{32}$') { Write-Error 'Invalid runtime pointer. Rerun setup.'; exit 3 }
$runtime = Join-Path $root ".career-agent/$relative"
if ((Get-Content (Join-Path $runtime '.project-root') -Raw).Trim() -ne $root) {
  Write-Error 'Project moved. Rerun setup; workspace files will be preserved.'; exit 3
}
& (Join-Path $runtime 'Scripts/python.exe') -m career_agent --project $root @args
exit $LASTEXITCODE
