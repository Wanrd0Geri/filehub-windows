# Independent Astra release review — pass 2

Reviewer: `/root/astra_release_review_final`, GPT-6 Astra, fresh context. Root transcribes the reviewer messages; reviewer does not modify source, index or installed state. Review is scoped to the release delta and Task 6 after the independent pass 1 fixes were approved.

## Pre-review at product head fc5a656

Reviewed product head: `fc5a656d03d2f0798eb7c0900399b494ca3a714e`. Packaging and final documentation were still in progress. **This is not final release approval.**

The reviewer found no additional Critical/Important code defect in the hidden-main duplicate notification and real-video self-test delta. It inspected the packaging spec, build and installer scripts, lifecycle helpers, source/notice materials, native screenshots and actual acceptance records. It independently hashed all 364 files against the candidate payload inventory and found no mismatch or extra file.

Evidence inspected included installed self-test (10 checks), source-native rule execution using the installed ffprobe, C-to-F move/F-to-C undo preserving main content, ADS and timestamps, whole-directory recycle, running-program upgrade/uninstall refusal, and successful same-version upgrade preserving 35 file hashes. Root separately read the completed manual-restore assertions in `native-recycle-evidence.json`; the earlier `native-recycle-shell.json` only proves the matching recycle item and available restore verb. These checks do not establish final rebuilt artifact acceptance, clean-VM compatibility, Mac execution or two-machine synchronization. An owned GUI-thread WM_QUIT was a graceful event-loop exit, not a tray mouse click.

## Important — incomplete attribution for shipped dependencies

1. Candidate `_internal/PySide6/opengl32sw.dll` was 20,639,544 bytes, SHA256 `34b444c016289b560662ff896deceb7f4b2c0723aed3d319ae167c9186ce42b3`. Its strings identify Mesa 11.2.2 and LLVM 3.6.2, but their notices were absent. The supplied QtBase/PySide sources do not contain those separate projects. Minimal correction: exclude the unused software OpenGL fallback after confirming the raster Widgets application does not need it, then revalidate the rebuilt application; alternatively supply the complete required materials.
2. Candidate `_internal/_decimal.pyd` includes libmpdec, but the shipped Python notices omitted Stefan Krah's copyright/BSD notice. The exact CPython v3.12.10 `Modules/_decimal/libmpdec/mpdecimal.h` includes the required binary redistribution notice. Retain decimal and ship the original upstream notice, including it in the preparation script, pinned manifest and license documentation.

The director assigned both corrections to the existing GPT-6.1 Sol packager as one scoped rebuild. XZ was considered; no concrete additional attribution blocker was established. Do not turn that observation into an unsupported finding.

## Scoped packaging correction — approved

The reviewer independently rechecked the corrected artifacts: all 364 files / 213,038,842 bytes match `sandbox/task6-final-payload-inventory.json`, with no mismatch or extra file. `opengl32sw.dll` is absent; the libmpdec notice is present and matches the original upstream text. The consolidated attribution finding is closed for these bytes.

- Portable executable SHA256: `49de4a22af285a7d03fa36658a8def165302faf3bb77034eebf14e2c6dc2b0d1`.
- Installer SHA256: `0de7a4cf0c246087318a60c9f77c782c1d05d684bc6d6ea22b7cc39efcb422f8`.

The reviewer inspected the final clean-installed 10-check self-test, refreshed native normal-launch evidence and actual HKCU registration/settings evidence. It also independently read the restored whole-directory test file (`owned tree content`) and checked that the restored empty directory exists. Twenty installed send processes, their durable requests, one claim/dialog and cancellation acknowledgement were inspected; the recorded source `InstanceLease` timing gate remains explicit.

## Final review pending

Final approval requires corrected payload/source-input manifests, rebuilt installer and executable hashes, affected installed launch/self-test evidence, remaining native integration and uninstall preservation evidence, accurate Chinese user documentation, and the exact final source SHA. Earlier core and unrelated acceptance tests need not be repeated unless a concrete correction affects them.
