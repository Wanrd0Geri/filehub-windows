# Independent Astra 0.3.1 final review

Review scope: stable functional delta `6ba2667e6508ea848b30d8fb94bdc2be117e0dfe..f36331fe604c9fcfb5bc443266c5201f168bcdce`, then metadata/documentation increment `f36331f..223ca6ea471bf71425cd50bdaaf6f7a750d3588b`, and the two-file repair increment `223ca6e..e454a028506d455a7f4f0af359c9173769eedae3`. This is a bounded 0.3.1 review, not a repeat of the 0.3.0 review.

Final source-review conclusion: **no unresolved actionable finding in the reviewed scope through 5f8865bdd486510d53de7daa9c8793f07537cae5**. Both independently reproduced findings below are closed by the repair increment and independent replay. Full-suite, fresh frozen-EXE and release-artifact validation are outside this reviewer's execution ownership and remain root/director-owned.

## Findings reproduced before repair (both now resolved)

1. **[P1] A durable manual archive is requeued when quitting before its callback.** `src/filehub/ui/archive_dialog.py:132-136`: `finished_result` now returns on `_live() == False`; `_live` includes `service._closing`. `Runtime.request_quit()` retires the service immediately while waiting for the serialized file worker, so a committed archive result arriving afterward never emits `execution_persisted` or settles the dialog. `Runtime._finish_quit` releases that claim. Reproduced through actual Runtime and SendQueue, actual preview and `service.execute`, then delayed only the callback delivery and requested quit. Observed `durable_ok=true`, `source_moved=true`, `runtime_closed=true`, `claim_redelivered=true`. On next launch the already processed selection resurfaces, pointing to moved source paths. Preserve same-service/state durable acknowledgement independently of presentation liveness, without resurrecting a closing UI or acknowledging a later claim.

2. **[P2] A partial recovery write leaves the same window unable to retry.** `src/filehub/service.py:88-94` and `src/filehub/ui/archive_dialog.py:85-87`: the adoption is durably committed before permission granting, but a grant failure only displays the error and retains the initial entry/candidate and initial controller snapshot. Reproduced through actual Runtime and confirmation dialog with one transient OSError injected only in `set_compatibility`; adoption ran normally. Disk generation became noninitial, while both dialog and controller stayed `initial`. A second explicit confirmation after removing the fault failed with `Catalogue changed; reload required`; permissions remained empty and Preview disabled. The recovery operation must reconcile the actual durable catalog after failure and permit another explicit attempt in the same tag window. This finding is the observed broken recovery behavior, not an objection to two transactions by itself.

Independent evidence: `sandbox/manual031/reviewer-8d6f1fdbadab4969b3940d7d0d6334a2/repro.py` and `repro.txt`. Both cases use owned state/material, no real user data, no registration, no installation. Executed with the existing `.venv/Scripts/python.exe -B -X utf8`, `PYTHONDONTWRITEBYTECODE=1`, explicit worktree `src` PYTHONPATH, and offscreen Qt. No full suite was run by this reviewer.

## Other reviewed paths

- Real Runtime poll only discovers profiles after a SendQueue claim; plain open remains independent of archive catalog inspection. Legacy and imported archive profiles route directly to ArchiveDialog. Empty/no-profile installations retain generic processing.
- Explicit recovery leaves ordinary imported rules disabled and configuration unchanged. Same-profile authority is unioned with manual permission; switching profiles requires an explicit choice and explains closing the prior profile's project routes. Catalog CAS and raw legacy backup behavior remain in force.
- Per-dialog, batch, queue and Runtime generation signal bindings prevent old dialogs from settling replacement/later claims. Existing generic-to-archive transfer keeps service/state/effective/page and claim identity checks.
- Closed or stale preview/recovery callbacks are guarded. Damaged catalog discovery falls back to generic with a visible recovery message; the main window remains reachable.
- Added selftest031 uses actual Runtime, queue, explicit restoration, history, actual archive and undo. QApplication is created at the self-test entry, rather than being supplied solely by a pytest singleton. Fresh frozen-EXE verification remains root/director-owned and is not claimed by this source review.
- Metadata increment includes the new selftest module in the packaging inventory and consistently changes app/installer/EXE version to 0.3.1. Updated docs distinguish same-profile permission preservation from profile switching and separate historical 0.3.0 validation claims. No additional actionable finding in this increment.

## Repair increment and independent replay

Reviewed only `223ca6e..e454a02`: ArchiveDialog and permanent regression tests. Durable completion now checks same service/state identity independently of presentation liveness, emits the persisted result and finishes its owned dialog even during retirement, while suppressing `show_result` during quit/close. Runtime's existing dialog/batch/queue/generation binding still controls which claim can be acknowledged; old-state callbacks cannot emit.

On recovery failure, a worker reads the actual catalog. The live/effective-generation checked callback updates both dialog and controller authority and reconciles the migration candidate; it does not grant permission. Another explicit confirmation is needed when the grant did not commit.

Independent replay used an unchanged copy of the original reviewer reproduction in a fresh owned directory, `sandbox/manual031/reviewer-bffd4aa991224bb4bfc313201721f828/repro.py`; output is `repro.txt`:

- QUIT: `durable_ok=true`, `source_moved=true`, `runtime_closed=true`, **`claim_redelivered=false`**.
- PARTIAL first failure: disk/UI/controller generations all match, Preview remains disabled, and the message says the actual settings were reread. After a second explicit confirmation: permissions are exactly `manual_archive`, Preview is enabled and the same dialog reports restored manual archiving.

No additional actionable finding in the repair increment. No full suite, packaging, installation, registry operation, live app shutdown, or real user state/material access was performed by this reviewer. Product source and Git/index were not edited by this reviewer; only the reviewer-owned evidence and this report were written.

Final micro-increment `e454a02..5f8865bdd486510d53de7daa9c8793f07537cae5` was separately read: one product line clears a stale `migration_error` only after a successful reread establishes a noninitial catalog; corresponding assertions cover that condition. No additional actionable finding. The original independent replay above remains evidence for e454a02; this one-line micro-increment was source-reviewed, not independently rerun.
