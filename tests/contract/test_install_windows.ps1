$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Installer = Join-Path $RepositoryRoot "scripts\install.ps1"
$FixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("career-agent-install-" + [guid]::NewGuid())
$Source = Join-Path $FixtureRoot "source"
$Target = Join-Path $FixtureRoot "consumer"

try {
    New-Item -ItemType Directory -Force -Path $Source | Out-Null
    Copy-Item -Recurse (Join-Path $RepositoryRoot "skills") (Join-Path $Source "skills")
    foreach ($name in @("career-rules.md", "AGENTS.md", "CLAUDE.md")) {
        Copy-Item (Join-Path $RepositoryRoot $name) (Join-Path $Source $name)
    }
    git -C $Source init -q
    git -C $Source add .
    git -C $Source -c user.name="Contract Test" -c user.email="contract@example.test" commit -qm fixture

    & $Installer -Source $Source -Target $Target -SkipPythonInstall -SkipDoctor -ForceMirror
    if ($LASTEXITCODE -ne 0) { throw "PowerShell installer failed" }

    $manifest = Get-Content (Join-Path $Target ".career-agent\install-manifest.json") -Raw | ConvertFrom-Json
    if ($manifest.mode -ne "mirror") { throw "Expected mirror mode" }
    $skill = Join-Path $Target ".agents\skills\career-setup\SKILL.md"
    if (-not (Test-Path $skill)) { throw "Codex skill was not installed" }

    & $Installer -Source $Source -Target $Target -SkipPythonInstall -SkipDoctor -ForceMirror
    if ($LASTEXITCODE -ne 0) { throw "PowerShell installer rerun failed" }
}
finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $FixtureRoot
}
