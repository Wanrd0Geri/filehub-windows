# Task 1 Sol report — templates and compatible routing

Status: implemented, focused verification GREEN, source frozen for Astra review. Worktree `C:/Users/Gerry-UltraPC/.codex/worktrees/filehub-rules/Hazel Windows`, branch `feature/filehub-rules-020`, dispatched base `1702617`. No staging, commits, installs, dependency changes, live app/state/registry operations or original F checkout writes. No full suite rerun; director/root owns the final suite.

## Owned changes

- New `src/filehub/templates.py`, `src/filehub/naming.py`, `tests/test_templates.py`.
- Narrow `rules.py` integration reuses existing discovery, tag parsing and legacy target builder.
- Narrow `service.py` integration owns the same-state store and binds/checks preview template digests.
- No UI, scheduler, operation engine or packaging changes. Other concurrent worktree files were not changed by this implementer.

## API contract

`ProjectTemplate` is frozen. Fields, in order: `id='default'`, `name='默认模板'`, `production_dir='3_制作'`, `asset_root='1_设定'`, `asset_categories={'角色':'角色','场景':'场景','道具':'道具'}`, `final_dir='4_交付'`, `keep_name_routes={'剧本':'2_剧本分镜','甲方':'0_甲方','参考':'_参考'}`, `test_dir='_测试'`, `naming_patterns={}`. Mappings are immutable copies. Category keys are tag keywords; their values are paths relative to asset_root, allowing e.g. `{'怪物':'生物/怪物'}`. Directory values are normalized safe relative paths with slash separators; absolute/drive/UNC/traversal/empty components/devices/invalid Windows characters are rejected. Naming modes are only shot/asset/final. Omit a mode to keep the existing naming implementation; an empty pattern is invalid.

`TemplateLibrary(templates=None-default-mapping, assignments={})` is frozen with read-only `.templates` (id→ProjectTemplate), `.assignments` (uppercase discovered project code→id), `.revision` (SHA256 of canonical versioned content). Real constructor default is the built-in mapping; pass mappings when supplying arguments. `.for_project(code)` compares project codes case-insensitively and falls back to built-in default. `.with_template(template)`, `.copy_template(id,new_id,name)`, `.assign(code,id)` and `.delete_template(id)` return new libraries. `.assign(code,None)` removes an assignment. The default cannot change/delete; assigned deletion is blocked. `.to_document()` returns mutable JSON-ready data; `TemplateLibrary.from_document(data)` validates schema, version, IDs, assignments and all templates. Use this explicit serialization instead of dataclasses.asdict on read-only mappings.

`TemplateStore(state_dir)` exposes `.state_dir`, `.path` (`templates.json`), `.load() -> TemplateLibrary`, `.save(library, expected_revision=None) -> TemplateLibrary`. Missing load creates neither directory nor file/lock and returns the fixed default digest. Existing loads and saves use the same per-state process lock as OperationEngine. Save validates before replacement, rechecks state/template/lock reparse paths, writes a state-local temporary file, flushes/fsyncs and atomically replaces. Any malformed existing document blocks save rather than resetting it. `expected_revision` provides optimistic stale-save rejection. To delete an assigned template, first save removal/reassignment, then delete/save; combining deletion and removal in one replacement cannot bypass the old saved assignment guard. Unsupported versions and duplicate IDs fail visibly. Document layout is `{'version':1,'templates':[...], 'assignments':{...}}`; JSON whitespace and list order do not alter the canonical content digest.

`naming.NAMING_TOKENS` is the finite frozenset. `validate_pattern(pattern, allowed_tokens=NAMING_TOKENS) -> str` returns the validated pattern. `render_pattern(pattern, values) -> str` validates and substitutes literal `{token}` only, then enforces one strict Windows component. Unknown tokens, access/indexing, conversion, Python format specs and malformed braces fail; no eval/format execution. `{sequence}` requires a nonnegative int (bool rejected). Absent optional values become empty. Literal/static and rendered device names are rejected, including CONIN$/CONOUT$ and device bases with spaces before extensions.

`parse_tag(tag, projects, sync_root, templates=None)` takes an immutable TemplateLibrary; it does no store I/O. `RouteSpec` appends defaulted `naming_pattern=''` and `template_revision=''`, preserving existing positional arguments. `build_targets` preserves the old branch exactly when the mode has no explicit pattern. Custom patterns use these values:

| Token | Value |
| --- | --- |
| original / stem / ext | Original component / stem / lowercase suffix including dot |
| prefix / note | Existing parsed prefix and cleaned note |
| date / date_long / period | Captured source time YYMMDD / YYYYMMDD / AM or PM |
| episode / scene | Decimal integer without padding, empty when absent |
| shot | First explicit/inferred shot decimal number plus optional letter, empty when absent |
| sequence | Lowest positive integer producing a free name under case-insensitive occupied-name checks |
| resolution | Existing width-derived tier, empty for non-video |

Custom naming need not require a team shot number or repeat legacy inferred date/version rules. An explicit custom pattern produces one target using the first available shot context; the unmodified legacy branch retains two-shot copy/move and three-shot warnings. A pattern without sequence rejects a collision rather than silently renaming. Directories retain their original names and existing keep-name collision handling, regardless of the custom pattern. Video modes still require valid width and use the existing tier boundaries.

`FileHubService.templates` is a TemplateStore built from `.engine.state_dir`; constructing it does not load templates. `.reload_templates() -> TemplateLibrary` explicitly loads current disk definitions and should run on the shared worker. Internal `._route(tag, templates=None)` also loads this store when no snapshot is supplied, so future automation consumers use the same state. Preview/execute supply one loaded immutable snapshot per call. `PreviewBatch` appends `template_revision=''`; service-generated previews always include the current digest. Execute loads from disk under the engine lock and rejects changed digest before any source mutation, even when another TemplateStore instance saved. Errors remain ordinary service outcomes/history. Manual legacy `PreviewBatch(tag,items)` with empty revision can execute only against the exact built-in default library; it cannot bypass custom-library checks. Normal/demo independence follows separately instantiated stores/services with separate state directories.

Example for the worker:

```python
library = service.reload_templates()
library = library.copy_template('default', 'my-project', '我的项目')
from dataclasses import replace
custom = replace(library.templates['my-project'], production_dir='制作/镜头',
                 asset_categories={'怪物': '生物/怪物'},
                 naming_patterns={'asset': '{prefix}_{date}_{sequence}{ext}'})
library = library.with_template(custom).assign('LYX', 'my-project')
saved = service.templates.save(library, expected_revision=service.reload_templates().revision)
preview = service.preview(selected_paths, 'LYX怪物龙')
# A later template save requires a new preview before execute.
```

## RED / GREEN evidence

Commands ran from the new worktree using its existing read-only venv junction and pytest's src pythonpath. Logs stay under its sandbox.

1. Initial RED: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_templates.py -q --basetemp=sandbox/rules020-task1-red` → expected new-module collection error `ModuleNotFoundError: No module named 'filehub.templates'`, 1 error. Log `sandbox/rules020-task1-red.txt`. This was import RED, not an assertion failure; subsequent behavior RED cycles below were ordinary assertion failures.
2. First integration run → 118 passed, 1 failed. The only failure was a new test fixture assuming template-list order and editing custom rather than default. Corrected the fixture to select default by ID; this was a test correction, not a production issue.
3. Additional RED `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_templates.py -q --basetemp=sandbox/rules020-task1-red2` → `test_ext_only_pattern_and_caller_token_whitelist` failed because `{ext}` was incorrectly rejected; 1 failed, 49 passed. Log `sandbox/rules020-task1-red2.txt`. Fixed validation's representative extension; renderer remains strict.
4. Additional RED same command with basetemp `sandbox/rules020-task1-red3` → `test_renderer_strict_single_component_and_optional_values` failed (`con .png` accepted); 1 failed, 51 passed. Log `sandbox/rules020-task1-red3.txt`. Fixed Windows device normalization/aliases.
5. Additional RED same command with basetemp `sandbox/rules020-task1-red4` → `test_store_rejects_reparse_lock_file` failed (load accepted a simulated reparse lock file); 1 failed, 52 passed. Log `sandbox/rules020-task1-red4.txt`. Added explicit checked_path before shared lock acquisition for store I/O.
6. Additional RED `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_templates.py::test_preview_reserves_custom_names_and_executes_snapshot -q --basetemp=sandbox/rules020-task1-red5` → internal service `_route` omitted assigned custom templates; 1 failed. Log `sandbox/rules020-task1-red5.txt`. Bound the no-snapshot internal route helper to reload_templates.
7. Final GREEN exact focused plan command: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_templates.py tests/test_rules.py tests/test_service.py -q --basetemp=sandbox/rules020-task1` → **137 passed in 3.07s**, exit 0. This contains 53 new template tests and all 84 existing rule/service regressions. Full output `sandbox/rules020-task1-green.txt`. `git diff --check -- src/filehub/rules.py src/filehub/service.py` produced no whitespace errors; only the repository's LF→CRLF informational warnings.

Coverage includes lazy absence/default exact filenames, immutable/copyable default, mappings/new category/project assignment, invalid schema/version/IDs/references, assigned deletion and optimistic saves, unsafe paths/patterns and atomic replace failure, strict renderer/devices, case-insensitive custom collision sequence, directory names, default merged/media rules via existing regressions, multi-input custom reservation/execution, external-store stale preview rejection, malformed JSON preservation, state/lock reparse guards and normal/demo store separation.

## Rulings and remaining boundaries

- Asset categories are keyword→relative-directory mappings rather than only a list; director explicitly approved the extension. Category prefix collisions choose longest keyword. Keep-name routes match the complete body. Case-insensitive duplicate keywords, category/keep-route same keywords and reserved grammar (PV/正片/成片/测试/E-digit/numeric beginnings) are rejected instead of shadowing routes. Existing dynamically discovered production sequence names retain the old parser precedence; users should keep these distinct from custom keywords.
- Default filename collision reallocation/history semantics remain unchanged as brief requires. Exact-target stale occupancy enforcement for generic automation belongs to later planner/runner tasks, not this legacy service change.
- Stale template rejection can record an empty journal batch and error outcomes, preserving service history semantics; it performs no material source/destination mutation.
- Template editing/UI worker wiring, demo callback invalidation and durable automation are later owned tasks. The new model/store itself has no GUI I/O and constructor performs no template file load.
- No new dependency, no packaging smoke and no full-suite result claimed in Task1.
