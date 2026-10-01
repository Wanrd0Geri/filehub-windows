# Workspace-only extraction. Does not run any installer or change registry/PATH.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskVendor = Join-Path $taskRoot 'sandbox/vendor-downloads'
New-Item -ItemType Directory -Force -Path $taskVendor | Out-Null
function GetPinned([string]$Name, [string]$Url, [string]$Hash) {
    $taskPath = Join-Path $taskVendor $Name
    if (!(Test-Path -LiteralPath $taskPath)) { Invoke-WebRequest $Url -OutFile $taskPath }
    if ((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLower() -ne $Hash) { throw "SHA256 mismatch: $Name" }
    return $taskPath
}
$taskInstaller = GetPinned 'innosetup-6.7.3.exe' 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' '9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732'
if ((Get-AuthenticodeSignature -LiteralPath $taskInstaller).Status -ne 'Valid') { throw 'Inno Authenticode not Valid' }
$taskUnpack = GetPinned 'innounp-2.zip' 'https://github.com/jrathlev/InnoUnpacker-Windows-GUI/releases/download/oi_2_2_11/innounp-2.zip' '851772538a041229102ad9964542d49dc00c74002e3091a70469c079ae368f52'
$taskUnpackDir = Join-Path $taskRoot 'sandbox/tools/innounp'
Expand-Archive -LiteralPath $taskUnpack -DestinationPath $taskUnpackDir -Force
Push-Location $taskRoot
try {
    & (Join-Path $taskUnpackDir 'innounp.exe') -x -y -b '-dsandbox/tools/inno-6.7.3' $taskInstaller
    if ($LASTEXITCODE) { throw 'Inno compiler extraction failed' }
} finally { Pop-Location }
Copy-Item -LiteralPath (Join-Path $taskRoot 'third_party/inno/ChineseSimplified.isl') -Destination (Join-Path $taskRoot 'sandbox/tools/inno-6.7.3/{app}/Languages/ChineseSimplified.isl') -Force
$taskMakeArchive = GetPinned 'make-4.4.1-3-x86_64.pkg.tar.zst' 'https://repo.msys2.org/msys/x86_64/make-4.4.1-3-x86_64.pkg.tar.zst' 'af0bdba17f06fe037f0194069adaa31a8fe45f1a11381501896aea1fae37bd5d'
$taskMakeDir = Join-Path $taskVendor 'make-msys-audit'
New-Item -ItemType Directory -Force -Path $taskMakeDir | Out-Null
& tar -xf $taskMakeArchive -C $taskMakeDir
if ($LASTEXITCODE) { throw 'GNU make extraction failed' }
if ((Get-FileHash -LiteralPath (Join-Path $taskMakeDir 'usr/bin/make.exe') -Algorithm SHA256).Hash.ToLower() -ne '91b7e155590d59db22e5eb0a3ffeec6350149f70f9ed2c242d133e584eb72fee') { throw 'GNU make executable hash mismatch' }
Write-Output 'Workspace-local Inno 6.7.3 and GNU make 4.4.1 prepared'
