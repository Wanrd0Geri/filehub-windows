# Task 6 Sol report — phase A (2026-10-01)

Prepared independent build/tool/license/assets only. Final frozen application build, installation, native registry/Shell integration, upgrade/uninstall, whole-suite verification and novice README/acceptance documents are **pending phase B**. No product-core/UI/entrypoint/tests/pyproject modifications, no real Desktop/Downloads/sync, no original Mac script execution, no remote publication, and no stage/commit yet.

## Prepared inputs

- Workspace `.venv` only: PyInstaller **6.19.0**, hooks **2026.8**, altgraph **0.17.5**, pefile **2024.8.26**, pywin32-ctypes **0.2.3**, setuptools **84.0.0**, packaging **26.3**. Installed within the controller-granted single-writer dependency window; pip process finished before UI phase B resumed. Existing Python **3.12.10**, PySide6 / Addons / Essentials / Shiboken **6.11.2** remain pinned. `packaging/build-requirements.txt` records exact versions.
- Official Inno Setup **6.7.3** compiler extracted into `sandbox/tools/inno-6.7.3/{app}`; no installer executed or registry setup. Download SHA256 `9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732`, Authenticode **Valid**, Pyrsys B.V. Licensed compiler and Simplified Chinese text from fixed official repository tag `is-6_7_3` are retained. Original Inno 7.1.0 workspace install attempt was rejected automatically before execution; latest unpacker could not read its 7.0.0.3 archive signature. Controller chose the supported 6.7.3 extractor route. No retry via installer wrapper.
- GNU make **4.4.1-3**, MSYS archive SHA256 `af0bdba17f06fe037f0194069adaa31a8fe45f1a11381501896aea1fae37bd5d`, executable SHA256 `91b7e155590d59db22e5eb0a3ffeec6350149f70f9ed2c242d133e584eb72fee`. Reused root-verified official MSYS2 bytes. Local MSVC x64 **19.44.35228**, Git Bash **5.3.15**; nothing installed system-wide or added to permanent PATH.
- Original app icon created locally with Qt vector drawing: `resources/app.ico`, 256px PNG frame inside standard ICO; actual QImage decode returned 256×256. No external artwork. No bundled font bytes; installed Inter / Noto Sans SC and system fallback are documented.
- Explicit valid self-test fixture `resources/selftest/tiny.mp4`: yellow 64×48 MPEG4, SHA256 `3d5addb83d23bc0d7de037e988509f6efd47286f3da9355a0670121a6eb1805b`. Generated using explicit development ffmpeg, only media fixture redistributed.

## ffprobe source/license closure

The root-downloaded BtbN shared LGPL3 candidate was inspected but **not selected**: its FFmpeg DLLs statically include many additional libraries. A license label alone did not establish their copyright/source closure.

Selected locally built **FFmpeg 8.1.3-filehub1**, LGPL-2.1-or-later, from exact upstream SHA `29e619e767cde9045a75c29bc9a8278ae7b3a98b`. Original source ZIP SHA256 is **`69ea98adb1b80aabdbecefdb0b545ff19ebcd7c6fc0cea9dd550b02f5b642a21`** (corrected a manually transcribed earlier milestone typo; scripts/manifest verify actual bytes). Two plainly disclosed source modifications in `third_party/ffprobe/filehub.patch`: localized MSVC compiler/archive banner recognition and propagation of `ff_mov_read_chnl` return value. Generated `config.h` compiler description becomes ASCII for Windows resource compiler compatibility. Modified version suffix `filehub1` appears in actual binary version output.

Build recipe disables external autodetection, x86 assembly, network inputs, other programs, encoders, muxers, device/filter and swscale/swresample libraries. It preserves built-in demuxers/decoders/parsers across the original MP4/MOV/M4V/MKV/WEBM/AVI range. An initial incremental rebuild after changing encoder/muxer configuration exposed stale MSVC archive members; recipe now runs `make clean` before build. Final clean build completed. Source/build lives solely in explicitly new owned `F:/FileHubTask6Build_01a0f5ae`, with ownership sentinel, because workspace spaces are unsuitable for FFmpeg make paths. Recipe refuses an existing unowned directory, never recursively deletes it, and can use another new space-free path.

Final binary hashes:

| File | SHA256 |
| --- | --- |
| `ffprobe.exe` | `ea9e0de482c11d74279857471aaa5467ce13a856d1b66ae42a8647bca67a3008` |
| `avcodec-62.dll` | `3265e25d662488e4fc17d0d995f7afe2a1b817fdc2638fdc6cdc520ac89d068b` |
| `avformat-62.dll` | `864789474b157a19b92dbf98a4431106051b3e377528066d27e07b9773739c30` |
| `avutil-60.dll` | `391f9c6fff14350cd8fd9f2965e3f9997e40577c12ccedc6523709a41e26dc95` |

MSVC `dumpbin /dependents` inspected all four files. Closure: the three supplied FFmpeg DLLs plus Windows **KERNEL32 / SHELL32 / bcrypt** only. No VC/UCRT dynamic runtime imports and no extra third-party DLL imports in this ffprobe build. Final GUI/Qt/Python distribution DLL closure remains a phase B gate; installed Visual Studio cannot be used to claim fresh-machine completeness.

`packaging/probe-smoke.py --generator C:/ffmpeg7.1.1/bin/ffmpeg.exe` generated six tiny fixtures and ran the **selected** ffprobe from separate sandbox cwd with PATH only `C:/WINDOWS/System32;C:/WINDOWS`, removing Python/venv/Qt inherited environment variables. All six returned width **64**, exit **0**, empty stderr: H264 MP4, MPEG4 MOV, MPEG4 M4V, H264 MKV, VP9 WEBM, MPEG4 AVI. Invalid media returned exit **1**. Additional HEVC MP4 returned codec `hevc`, width **64**. Evidence `sandbox/task6-media-probes/result.json`, `dll-imports.json`, `tiny-hevc.mp4`; this is process-isolated native Windows evidence, **not final packaged application or fresh VM acceptance**.

## Compile warnings (explicitly assessed)

Final log `sandbox/vendor-downloads/ffprobe-msvc-final-clean.log` has **99** upstream MSVC warnings: C4090×3, C4101×4, C4113×33, C4293×3, C4319×1, C4333×3, C4334×50, C5287×2. C4700 uninitialized MOV return was real and fixed; it is absent in the final build. C4293 is in IWHT macro instantiation with `bits=0`, where the warned negative shift is the unselected constant conditional branch. C4113 largely concerns `restrict` qualifiers on DSP function pointers. C4333 refers to Windows color-table terminal formatting rather than extracted media metadata. Remaining warnings concern widening/sign extension, unused legacy-codec locals, qualifiers and enum comparisons. They are retained rather than globally suppressed; representative H264/HEVC/VP9 probes succeeded, which does not validate every legacy decoder. The configure warning “pkg-config not found” is recorded: external autodetection is disabled and final import closure contains no external library. No product safety guarantees were weakened to hide compiler warnings.

## Offline source and notice materials

- `docs/第三方许可.md`, `third_party/components.json`, Python/embedded-library, Qt/PySide, FFmpeg, PyInstaller, Inno and Microsoft notices prepared. QtBase **86** and PySide **6** full upstream attribution entries with every referenced license file were copied verbatim. Qt metadata raw multiline descriptions required JSON `strict=False`; metadata files themselves were unchanged. Whole-source attribution inventory includes unused upstream components and is clearly labeled reference scope.
- Explicit source ZIPs are added to PyInstaller data under `third_party/sources`: FFmpeg **23,134,216 bytes**, QtBase **78,663,969 bytes**, PySide **23,050,410 bytes**. SHA256s and exact commits are pinned in manifest; no entire sandbox/repository inclusion. Corresponding-source delivery is offline inside the program payload. FFmpeg build scripts/patch accompany it. Source archives stay ignored in sandbox rather than introducing large upstream archives into Git.
- QtBase source ZIP SHA256 `02d5195d165949318340d27fee6c28d047f0d4682b40c8fa75509a785e686051`, commit `ef55f427f2c8b410d34f8a7681020a3000cf6866`; PySide source ZIP SHA256 `7c357b79dcc0e38da49bcd667dedf342ff7b2c557e2e858dea2a5690f80a37e7`, commit `24627cd36e1593adf22eb1f2950e4248e7bcc1ec`. LGPL3/GPL3 texts included from fixed upstream source. Shared onedir libraries can be replaced with compatible modifications; no application prohibition on LGPL reverse engineering/debugging.

## Build/installer preparation verification

- `packaging/entrypoint.py` uses `runpy.run_module('filehub', run_name='__main__')`, preserving relative imports. PyInstaller onedir spec explicitly lists icon, tiny fixture, notices, sources and ffprobe binaries (no duplicate `third_party/bin` payload). Qt image plugins restricted to QtBase GIF/ICO/JPEG/WBMP; Qt runtime DLLs limited to Core/Gui/Widgets. Final analysis/runtime verifies this scope before acceptance.
- Chinese installer current-user, optional unchecked context/startup/desktop tasks, normal and isolated `--demo` Start menu shortcuts, no implicit application launch. Upgrade and uninstall use the agreed `Local/FileHub.Windows.v1.ProgramInUse` mutex to request graceful tray quit; never force termination. Registration/uninstall checks owner, expected executable and unchanged commands/Run values; foreign-modified entries are preserved. User state/project data are outside install manifest and no uninstall-delete sweep exists.
- Syntax-only Inno compile used official harmless example executable as placeholder under `sandbox/task6-installer-syntax`, **never installed or launched**. `ISCC /DPayloadRoot=... /O... packaging/installer.iss` successful in **0.797s** with Chinese language and all code compiled; draft installer is not deliverable.
- `packaging/prepare-tools.ps1` successfully repeated noninteractive extraction, SHA/signature checks and GNU make preparation. An initial repeat waited on unpacker overwrite prompt; owned helper/parent were stopped and recipe corrected with `-y -b`; repeat completed. `prepare-sources.ps1` verified all three original source archives. All four PowerShell scripts parse successfully; all eight Python/spec files parsed with `ast.parse`.
- `freeze-input-manifest.py`: **209** fixed file hashes and **3** source archives. `verify-inputs.py`: **Pinned runtime and notice input hashes verified**. Build never silently refreshes manifest; maintainer freeze command is separate.

## Phase B plan at phase-A boundary (superseded by completed results below)

Wait for stable reviewed runtime before final PyInstaller/installer build. Coordinate PySide6 runtime dependency declaration in `pyproject.toml` (currently omitted), maintain exact build lock. Verify actual distribution imports/MSVC redistributable DLLs and produce final payload inventory, then clean child-environment installed self-test. Use original ten-case real1920 video naming evidence, distinct second-video content, all safety boundary acceptance, screenshots, pause/resume/background, actual shortcuts, owned isolated registry/native Shell single-file + separately labeled multi-process aggregation, install → first launch → archive/undo → upgrade → uninstall preserving state/history/project/source. No fresh VM, Mac or dual-machine sync claims. Write Chinese README/usage/acceptance table only after results. Final full suite once after final inputs, independent review, impacted rebuild/retests, scoped commit only when controller grants Git-index window.


## Phase B completed — 2026-10-01 final evidence

产品冻结于 `fc5a656d03d2f0798eb7c0900399b494ca3a714e`。最终包装审查排除了未使用的 `opengl32sw.dll`（Mesa 11.2.2 / LLVM 3.6.2）；应用只使用 raster Widgets。CPython 3.12.10 内嵌 libmpdec 的版权与 BSD 条件保存在 `third_party/python/libmpdec-LICENSE.txt`。冻结后没有改产品行为。PySide6 依赖固定为 6.11.2，manifest 包含 212 个固定输入与 3 个源码档案，build 只验证，绝不隐式刷新。

**已证实的启动失败根因是 ICU**：初始 PyInstaller 继承 Codex PATH，误收集 Poppler ICU78 的版本改名导出；Qt 需要 Windows 的无版本 ICU 导出。移除自有候选包中的外来 ICU 后，真实 selftest 通过；恢复 CPython 原本 VC 14.42 后仍通过，所以 VC 不兼容只是已被证伪的诊断假设。最终 build 清洁子进程 PATH / 环境并过滤 ICU、API-set 与无关插件，实际加载 Windows System32 ICU。早期失败候选与残留旧 DLL 的诊断覆盖安装均不作为最终证据，最终包经过旧候选 native 卸载后干净安装。

最终构建日志 `sandbox/task6-final-license-build.log`，Inno 编译成功，用时 20.688s。便携 payload 为 364 个文件、213,038,842 bytes，未解析 import 名称为空；实际 GUI 模块加载另外确认了运行时解析。最终 post-filter COLLECT 有 55 项二进制来源，无 Poppler / Libheif / Mesa；初期 Analysis TOC 的诊断清单已被替代。VC 文件来自 CPython / PySide / Shiboken wheel，带 Microsoft 材料；实际 root VCRUNTIME140 为 14.42.34438，PySide / Shiboken 为 14.44.35211，没有依靠系统 VS 的运行库。逐文件 SHA256 保存在最终 inventory。

最终 0.1.0 交付：

- 安装器 `dist/installer/FileHub-0.1.0-windows-x64-setup.exe`，139,798,744 bytes，SHA256 `0de7a4cf0c246087318a60c9f77c782c1d05d684bc6d6ea22b7cc39efcb422f8`。
- 便携 `dist/FileHub/FileHub.exe`，2,330,634 bytes，SHA256 `49de4a22af285a7d03fa36658a8def165302faf3bb77034eebf14e2c6dc2b0d1`；须保留整个目录。

最终便携与安装版在 clean child PATH、独立 cwd、fake LOCALAPPDATA 下自测 exit0，10 项全部 true。实际 bundled probe 检出 64 宽样例及两段不同 1920 H264 视频；LYX020822 归入 E02/S08，命名为 1080p、`_01` / `_02`，双撤销通过。安装版普通／演示／后台都实际启动，截图记录中文首次暂停 UI 与隔离演示。最终安装版自有主窗口 WM_CLOSE 后隐藏而进程保持活跃，次进程重新显示窗口后 exit0；最后自有 GUI 线程 WM_QUIT 在 coordinator 等待结束后 exit0。没有声称鼠标点击托盘退出。

原始规则 source FileHubService harness 使用真实 PNG / 媒体、安装目录实际 ffprobe、真实源创建时间与本地时区。两镜／三镜、PNG、苏云法相／破败庠序／新角色／PV、无效口令一次通知都通过，重新建立 service 后撤销通过。真实去重回收保留了已有项目 survivor，结果显示该路径，历史明确提示手动还原；Shell 精确还原自有项并核对 hash。整目录回收在 Shell Namespace10 中只有一个自有项，包含空目录；undelete 后仅将自有 staging 改回 origin，内容保留。真 C↔F 跨盘移动与撤销保留主内容、ADS、创建／修改时间。上述 source harness 不冒称安装版鼠标操作；受控时间与故障注入不等同真实三天、断电或系统回收失败。

Native Shell.Application 枚举并调用唯一自有单文件 verb，安装程序收到一个对话框；临时 QA verb 已精确删除。20 个安装版 send 子进程 exit0、持久保存 20 请求；初始时序用 source InstanceLease 门禁控制，primary 只有一个 dialog、一个 claim token、20 个独立路径。取消后队列清零，再正常退出。分类为 native Shell 单文件与多进程聚合，没有 Explorer 鼠标多选声明。source Qt Runtime 设置 widgets 与实际 HKCU 证明了 context / Run 开关以及暂停／恢复配置和 tray 状态，没有安装版鼠标设置声明。

安装版 GUI 活跃时升级和卸载都 exit1，程序完整；退出后同版升级 exit0，35 个状态／历史／项目／源文件 SHA256 不变。`/GROUP=<uniqueQA>` 被 DisableProgramGroupPage 忽略，实际开始菜单 group 是 FileHub；安装日志证明是本次新建目录。两个 `.lnk` 的目标与参数已记录，演示参数为 `--demo`。最终干净安装实际启用了 optional context / autostart，验证了 quoted command 和 Player。

最终 native 卸载 exit0，104 个状态／历史／项目／源文件 SHA256 保留，程序及自有快捷方式移除。自有注册被受控写成 foreign command / Run 后，卸载保留这些值；验证后精确清理 fixture。首个清理验证删除 fixture 值后，因安装器有意保留被改命令的整项 metadata，遇到过严的 absent-key 断言；随后只清理精确捕获的自有 metadata。最终 context / Run / Start Menu 均恢复 absent。未强杀进程，未操作真实用户素材目录。

controller 在最终冻结后独占执行 `.venv/Scripts/python.exe -X utf8 -m pytest -q --basetemp=sandbox/task6-final-suite`，**255 passed in 20.69s，exit0**。[原始输出](../evidence/task6-final-pytest.txt)。之前 248 项与 focused 93 / runtime 29 属于更早证据阶段，不替代最终 gate，也没有重复最终 suite。

持久证据与截图位于 `docs/evidence/task6/`，完整分类见 [验收结果](../验收结果.md)；[使用说明](../使用说明.md) 已交付。root 独立核对 [artifact 版本、hash 与许可材料](../evidence/root-final-artifact-audit.json)。完整 QA 日志和 snapshots 保存在 `sandbox/task6-acceptance/d26ef8d9820b41e2a3e1e93da787377f`，新的 C UUID fixture 及 F fixture 路径已记录并保留。Windows 10 / 全新 VM / Mac / 真实双机百度同步仍未验证；当前本机 Windows 11 x64 build 26200。QA 程序已卸载，最后 scoped index / commit 等控制方窗口，本 agent 没有 stage / commit / push / merge。
