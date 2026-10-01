# FileHub 0.2.2 final acceptance

Completed within the authorized two changes: automatic image conversion collision numbering and the day-input/scrollbar UI adjustment. Frozen source and build metadata: `681bc6965617f7791bf22635b7045f36c15689c5`. Later commits contain acceptance evidence and documentation only.

- Root's single full source suite: **733 passed in 61.91 seconds, exit 0**. [Raw output](../../evidence/rules-022/root-full-suite.txt).
- Actual packaged EXE in a clean, hidden, UUID-owned environment: **23/23 checks true, exit 0, runtime_frozen=true**. This retains the original 21 checks and adds numbered conversion replacement/backup/undo plus refusal of a target occupied after preview. [Actual report](../../evidence/rules-022/packaging-portable-selftest.json).
- Fresh independent Astra source review: no blocker. [Review](root-astra-review.md). Director's implementation review and native UI evidence are [separate](astra-source-review.md).
- Root's independent read-only artifact audit: **passed**, all **47 FileHub PYZ modules** equal frozen source; EXE and installer PE versions are **0.2.2.0**; reviewed material hashes, manifest, sole qwebp plugin and retained 0.2.1 installer verified. No excluded payload found. [Audit](../../evidence/rules-022/root-final-artifact-audit.json).

Installer: `FileHub-0.2.2-windows-x64-setup.exe`, 143140953 bytes, SHA256 `705bf74f3567c73fe152e907d0726a438a1784b0f1ffac58c83886c74b7fc33f`. Root saved it and installation instructions to `F:/FileHub交付/0.2.2` and verified the copied installer hash. Existing 0.2.1 and 0.2.0 installer bytes remain unchanged.

Source/native-window checks and packaged runtime self-tests are distinct evidence scopes. No new live install/upgrade/uninstall matrix was run. No existing process stop, user state/watch/registry change, dependency update, push, merge or shutdown occurred. Owned build/self-test/UI processes completed normally. The user performs any upgrade. Windows 10, clean VM, Mac and real dual-machine synchronization remain unverified.
