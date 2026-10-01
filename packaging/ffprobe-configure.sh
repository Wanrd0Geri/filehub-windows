#!/usr/bin/env bash
set -eu
export PATH="$(cygpath -u "${FILEHUB_MSVC_BIN:-C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64}"):/usr/bin:$PATH"
build_root=$(cygpath -u "${FILEHUB_FFMPEG_BUILD:-F:/FileHubTask6Build_01a0f5ae}")
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$build_root/source"
./configure --toolchain=msvc --arch=x86_64 --target-os=win64 \
  --disable-autodetect --disable-x86asm --disable-doc --disable-debug \
  --disable-programs --enable-ffprobe --disable-encoders --disable-muxers \
  --disable-avdevice --disable-avfilter \
  --disable-swscale --disable-swresample --disable-network \
  --enable-shared --disable-static --extra-version=filehub1 \
  --prefix="$build_root/install"
# This MSVC installation has only Chinese banner resources. The RC compiler
# cannot consume that UTF-8 banner inside config.h; normalize the diagnostic.
sed -i 's/^#define CC_IDENT .*/#define CC_IDENT "Microsoft MSVC 19.44.35228 x64"/' config.h
"$script_root/../sandbox/vendor-downloads/make-msys-audit/usr/bin/make.exe" clean
"$script_root/../sandbox/vendor-downloads/make-msys-audit/usr/bin/make.exe" -j8
"$script_root/../sandbox/vendor-downloads/make-msys-audit/usr/bin/make.exe" install
