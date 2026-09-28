param(
    [string]$Source = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Target = $Source,
    [switch]$ForceMirror,
    [switch]$AllowDirtySource,
    [switch]$SkipPythonInstall,
    [switch]$SkipDoctor,
    [switch]$SimulateValidationFailure,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$arguments = @(
    (Join-Path $PSScriptRoot "install_support.py"),
    "--source", $Source,
    "--target", $Target
)
if ($ForceMirror) { $arguments += "--force-mirror" }
if ($AllowDirtySource) { $arguments += "--allow-dirty-source" }
if ($SkipPythonInstall) { $arguments += "--skip-python-install" }
if ($SkipDoctor) { $arguments += "--skip-doctor" }
if ($SimulateValidationFailure) { $arguments += "--simulate-validation-failure" }
if ($Uninstall) { $arguments += "--uninstall" }

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uv) {
    $candidate = Join-Path $env:USERPROFILE '.local/bin/uv.exe'
    if (Test-Path $candidate) { $uv = Get-Item $candidate }
}
if ($null -eq $uv) { Write-Error 'Setup needs uv. See https://docs.astral.sh/uv/getting-started/installation/'; exit 3 }
$uvPath = if ($uv.Source) { $uv.Source } else { $uv.FullName }
$env:PATH = "$(Split-Path $uvPath)$([IO.Path]::PathSeparator)$env:PATH"
& $uvPath run --no-project --python 3.12 @arguments
exit $LASTEXITCODE
