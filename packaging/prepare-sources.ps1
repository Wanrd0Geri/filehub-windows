[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskVendor = Join-Path $taskRoot 'sandbox/vendor-downloads'
New-Item -ItemType Directory -Force -Path $taskVendor | Out-Null
$taskSources = @(
    @('ffmpeg-source.zip','https://codeload.github.com/FFmpeg/FFmpeg/zip/29e619e767cde9045a75c29bc9a8278ae7b3a98b','69ea98adb1b80aabdbecefdb0b545ff19ebcd7c6fc0cea9dd550b02f5b642a21'),
    @('qtbase-source.zip','https://codeload.github.com/qt/qtbase/zip/refs/tags/v6.11.2','02d5195d165949318340d27fee6c28d047f0d4682b40c8fa75509a785e686051'),
    @('pyside-source.zip','https://codeload.github.com/pyside/pyside-setup/zip/refs/tags/v6.11.2','7c357b79dcc0e38da49bcd667dedf342ff7b2c557e2e858dea2a5690f80a37e7')
)
foreach ($taskEntry in $taskSources) {
    $taskPath = Join-Path $taskVendor $taskEntry[0]
    if (!(Test-Path -LiteralPath $taskPath)) { Invoke-WebRequest $taskEntry[1] -OutFile $taskPath }
    if ((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLower() -ne $taskEntry[2]) { throw "Source SHA256 mismatch: $($taskEntry[0])" }
}
Write-Output 'Three explicit corresponding-source archives verified'
