[CmdletBinding()]
param(
    [string]$BuildRoot = 'F:/FileHubTask6Build_01a0f5ae',
    [string]$VcVars = 'C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat',
    [string]$MsvcBin = 'C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskVendor = Join-Path $taskRoot 'sandbox/vendor-downloads'
$taskSource = Join-Path $taskVendor 'ffmpeg-source.zip'
$taskExpected = '69ea98adb1b80aabdbecefdb0b545ff19ebcd7c6fc0cea9dd550b02f5b642a21'
New-Item -ItemType Directory -Force -Path $taskVendor | Out-Null
if (!(Test-Path -LiteralPath $taskSource)) {
    Invoke-WebRequest 'https://codeload.github.com/FFmpeg/FFmpeg/zip/29e619e767cde9045a75c29bc9a8278ae7b3a98b' -OutFile $taskSource
}
if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLower() -ne $taskExpected) { throw 'FFmpeg source SHA256 mismatch' }
$taskMake = Join-Path $taskVendor 'make-msys-audit/usr/bin/make.exe'
if (!(Test-Path -LiteralPath $taskMake)) { throw 'Extract verified make-4.4.1-3-x86_64.pkg.tar.zst into sandbox/vendor-downloads/make-msys-audit first' }
if ((Get-FileHash -LiteralPath $taskMake -Algorithm SHA256).Hash.ToLower() -ne '91b7e155590d59db22e5eb0a3ffeec6350149f70f9ed2c242d133e584eb72fee') { throw 'GNU make executable SHA256 mismatch' }
if (!(Test-Path -LiteralPath $VcVars)) { throw 'MSVC x64 build tools required for developer source build' }
$taskAbsolute = [System.IO.Path]::GetFullPath($BuildRoot)
if ($taskAbsolute -match '\s') { throw 'FFmpeg source build directory must have no spaces' }
$taskSentinel = Join-Path $taskAbsolute 'FILEHUB-BUILD-OWNER.txt'
if (Test-Path -LiteralPath $taskAbsolute) {
    if (!(Test-Path -LiteralPath $taskSentinel) -or (Get-Content -LiteralPath $taskSentinel -Raw).Trim() -ne $taskExpected) {
        throw 'Existing build directory is not owned by this recipe; choose a new path'
    }
} else {
    New-Item -ItemType Directory -Path $taskAbsolute | Out-Null
    Set-Content -LiteralPath $taskSentinel -Value $taskExpected -Encoding ascii
    Expand-Archive -LiteralPath $taskSource -DestinationPath (Join-Path $taskAbsolute 'unpack')
    Move-Item -LiteralPath (Join-Path $taskAbsolute 'unpack/FFmpeg-29e619e767cde9045a75c29bc9a8278ae7b3a98b') -Destination (Join-Path $taskAbsolute 'source')
    & (Join-Path $taskRoot '.venv/Scripts/python.exe') -X utf8 (Join-Path $PSScriptRoot 'patch-ffmpeg.py') (Join-Path $taskAbsolute 'source')
    if ($LASTEXITCODE) { throw 'Source patch failed' }
}
$env:FILEHUB_FFMPEG_BUILD = $taskAbsolute
$env:FILEHUB_VCVARS = $VcVars
$env:FILEHUB_MSVC_BIN = $MsvcBin
try {
    & (Join-Path $PSScriptRoot 'ffprobe-build-local.cmd')
    if ($LASTEXITCODE) { throw 'FFprobe source build failed' }
    $taskOutput = Join-Path $taskRoot 'third_party/ffprobe/bin'
    New-Item -ItemType Directory -Force -Path $taskOutput | Out-Null
    Get-ChildItem (Join-Path $taskAbsolute 'install/bin') | Where-Object Extension -in '.exe','.dll' | Copy-Item -Destination $taskOutput
} finally {
    Remove-Item Env:FILEHUB_FFMPEG_BUILD,Env:FILEHUB_VCVARS,Env:FILEHUB_MSVC_BIN -ErrorAction SilentlyContinue
}
