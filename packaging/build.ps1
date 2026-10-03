[CmdletBinding()]
param(
    [string]$ISCC = '',
    [switch]$PortableOnly
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $taskPython)) { throw 'Missing workspace .venv Python' }
if (!(Test-Path -LiteralPath (Join-Path $taskRoot 'src/filehub/__main__.py'))) {
    throw 'Runtime entry has not been integrated; phase A cannot make a final package.'
}
Push-Location $taskRoot
$taskOriginalPath = $env:PATH
$taskEnvironment = @{}
Get-ChildItem Env: | Where-Object { $_.Name -match '^(QT_|PYSIDE)' -or $_.Name -in @('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','PYTHONDONTWRITEBYTECODE') } | ForEach-Object {
    $taskEnvironment[$_.Name] = $_.Value
    Remove-Item -LiteralPath ('Env:'+$_.Name)
}
$env:PATH = (Join-Path $taskRoot '.venv/Scripts')+';'+(Join-Path $env:SystemRoot 'System32')+';'+$env:SystemRoot
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=Join-Path $taskRoot 'src'
try {
    & $taskPython -B -X utf8 (Join-Path $PSScriptRoot 'verify-inputs.py')
    if ($LASTEXITCODE) { throw 'Build input gate failed' }
    & $taskPython -B -X utf8 -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller packaging/filehub.spec
    if ($LASTEXITCODE) { throw 'PyInstaller failed' }
    if (!$PortableOnly) {
        if (!$ISCC) { $ISCC = Join-Path $taskRoot 'sandbox/tools/inno-6.7.3/{app}/ISCC.exe' }
        if (!(Test-Path -LiteralPath $ISCC)) { throw 'Pass -ISCC with workspace-local Inno compiler' }
        & $ISCC (Join-Path $PSScriptRoot 'installer.iss')
        if ($LASTEXITCODE) { throw 'Inno compiler failed' }
    }
    & $taskPython -B -X utf8 (Join-Path $PSScriptRoot 'create-rule-guide.py') --output dist/FileHub-rule-guide-v1.zip
    if ($LASTEXITCODE) { throw 'Rule guide bundle failed' }
    $taskFiles = @(Get-Item dist/FileHub/FileHub.exe,dist/FileHub-rule-guide-v1.zip)
    if (!$PortableOnly) { $taskFiles += Get-Item dist/installer/FileHub-0.3.0-windows-x64-setup.exe }
    $taskFiles | ForEach-Object {
        [pscustomobject]@{ file = $_.FullName; bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower() }
    } | ConvertTo-Json | Set-Content dist/artifacts.json -Encoding utf8
} finally {
    $env:PATH = $taskOriginalPath
    foreach ($taskName in @('PYTHONPATH','PYTHONDONTWRITEBYTECODE')) { Remove-Item -LiteralPath ('Env:'+$taskName) -ErrorAction SilentlyContinue }
    foreach ($taskName in $taskEnvironment.Keys) { Set-Item -LiteralPath ('Env:'+$taskName) -Value $taskEnvironment[$taskName] }
    Pop-Location
}
