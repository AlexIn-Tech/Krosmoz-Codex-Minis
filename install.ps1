# Run from a repository clone: .\install.ps1 goultard
# Options pass through to the shared Python installer.
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install.py'
if (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 $installer @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $installer @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $installer @args
} else {
    throw 'Install Python 3.9 or newer, then run this script again.'
}
exit $LASTEXITCODE
