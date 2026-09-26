param(
    [string]$Source = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Target = $Source,
    [switch]$ForceMirror,
    [switch]$AllowDirtySource,
    [switch]$SkipPythonInstall,
    [switch]$SkipDoctor,
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
if ($Uninstall) { $arguments += "--uninstall" }

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    $python = Get-Command py -ErrorAction Stop
    & $python.Source -3 @arguments
} else {
    & $python.Source @arguments
}
exit $LASTEXITCODE
