$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Installer = Join-Path $RepositoryRoot "scripts\install.ps1"
$FixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("career-agent-install-" + [guid]::NewGuid())
$Source = Join-Path $FixtureRoot "source"
$Target = $Source

try {
    New-Item -ItemType Directory -Force -Path $Source | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $Source ".agents") | Out-Null
    Copy-Item -Recurse (Join-Path $RepositoryRoot ".agents\skills") (Join-Path $Source ".agents\skills")
    git -C $Source init -q
    git -C $Source add .
    git -C $Source -c user.name="Contract Test" -c user.email="contract@example.test" commit -qm fixture

    & $Installer -Source $Source -Target $Target -SkipPythonInstall -SkipDoctor -ForceMirror
    if ($LASTEXITCODE -ne 0) { throw "PowerShell installer failed" }

    $manifest = Get-Content (Join-Path $Target ".career-agent\install-manifest.json") -Raw | ConvertFrom-Json
    if ($manifest.installed_modes.claude_code -ne "mirror") { throw "Expected mirror mode" }
    if ($manifest.installed_modes.codex -ne "canonical") { throw "Expected canonical Codex mode" }
    $skill = Join-Path $Target ".agents\skills\career-onboard\SKILL.md"
    if (-not (Test-Path $skill)) { throw "Canonical Codex skill was not found" }
    $claudeSkill = Join-Path $Target ".claude\skills\career-onboard\SKILL.md"
    if (-not (Test-Path $claudeSkill)) { throw "Claude mirror was not installed" }

    & $Installer -Source $Source -Target $Target -SkipPythonInstall -SkipDoctor -ForceMirror
    if ($LASTEXITCODE -ne 0) { throw "PowerShell installer rerun failed" }
}
finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $FixtureRoot
}
