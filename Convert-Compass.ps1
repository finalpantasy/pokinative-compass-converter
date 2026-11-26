# Compass Converter for PokiNative: asks for the two folders (or takes them as arguments) and runs the converter with
# the Python that the PokiNative launcher installed. Started by Convert-Compass.cmd.
param([string]$Compass, [string]$PokiNative, [switch]$Check)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$settingsDir = Join-Path $env:LOCALAPPDATA 'pokinative-compass-converter'
$settingsFile = Join-Path $settingsDir 'last-folders.json'
$last = @{}
if (Test-Path $settingsFile) {
    try { (Get-Content $settingsFile -Raw | ConvertFrom-Json).psobject.Properties | ForEach-Object { $last[$_.Name] = $_.Value } } catch {}
}

function Select-Folder([string]$title, [string]$start) {
    Add-Type -AssemblyName System.Windows.Forms
    $d = New-Object System.Windows.Forms.FolderBrowserDialog
    $d.Description = $title
    $d.ShowNewFolderButton = $false
    if ($start -and (Test-Path $start)) { $d.SelectedPath = $start }
    if ($d.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return $null }
    return $d.SelectedPath
}

if (-not $PokiNative) {
    $PokiNative = Select-Folder 'Choose your PokiNative folder (the target folder you picked in the PokiNative launcher)' $last['pokinative']
    if (-not $PokiNative) { Write-Host 'Cancelled.'; exit 1 }
}
if (-not $Compass) {
    $Compass = Select-Folder 'Choose the Pokemon Compass folder you unpacked from your download' $last['compass']
    if (-not $Compass) { Write-Host 'Cancelled.'; exit 1 }
}
New-Item -ItemType Directory -Force $settingsDir | Out-Null
@{ pokinative = $PokiNative; compass = $Compass } | ConvertTo-Json | Set-Content -Encoding utf8 $settingsFile

# The launcher's Python sits in <install>\python; the install may be the chosen folder or one level below it.
$python = $null
foreach ($c in @($PokiNative) + @(Get-ChildItem -Directory $PokiNative -ErrorAction SilentlyContinue | ForEach-Object FullName)) {
    $p = Join-Path $c 'python\python.exe'
    if (Test-Path $p) { $python = $p; break }
}
if (-not $python) { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $python) { Write-Host "No Python found in $PokiNative\python. Build the game in the PokiNative launcher first."; exit 1 }

$cmdArgs = @('-I', (Join-Path $here 'compass_to_pokinative.py'), '--compass', $Compass, '--pokinative', $PokiNative)
if ($Check) { $cmdArgs += '--check' }
& $python @cmdArgs
exit $LASTEXITCODE
