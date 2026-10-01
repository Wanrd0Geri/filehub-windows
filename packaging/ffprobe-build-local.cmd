@echo off
setlocal
if not defined FILEHUB_VCVARS set "FILEHUB_VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
call "%FILEHUB_VCVARS%"
if errorlevel 1 exit /b 1
"C:\Program Files\Git\usr\bin\bash.exe" "%~dp0ffprobe-configure.sh"
exit /b %errorlevel%
