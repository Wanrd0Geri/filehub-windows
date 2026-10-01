# Task 2 Astra stage review

Head `ce10b1b9b56d296cfcb9fb5dc088bbee59dba7b6`. Reported full suite 131 passed (47 rule cases + 84 core), 5.05s. Read report, compatibility contract and rules implementation; did not rerun existing tests. No original Mac execution.

**Spec/quality: Needs fixes.** Core case coverage, fixed timestamp injection, semantic collision allocation and platform-independent rules are in place. Two behavior divergences remain:

1. `build_targets` says directories preserve names, but the shared `target()` helper always runs `safe_name`. A valid Windows directory with an emoji or mathematical character gets renamed even when global name cleanup is off. Validate directory components without sanitizing their original base; preserve it through collision suffixing too. Cover real Unicode directories for keep and dated.
2. Merged-shot selection and warnings use `video`, while original `cmd_route` generates copies/warnings only when `uses_team_name` is true (episode+scene video). E01C3+4/PV extensions now create extra files outside the source rule. Restrict merged copy and >=3 warning to the original team branch; use only the first mirror on other routes. PV/正片 parsing should apply the approved lost-C-shot fix without adding unrequested `+` or suffix parsing semantics; original trailing text remains note. Update compatibility notes and add regression cases.

Fix round1 sent to the same GPT-6.1 Sol. No change requested to the approved transaction engine.

## Scoped fix review — approved
Head 0dfa0120f1936c4ea2c83398644a568546d8c7b6. Reviewed ce10b1b..0dfa012 diff, regression cases and compatibility notes. Directory original Unicode survives target allocation and collision suffixing; copy/warning scope is restored to ep+scene team video; PV numeric-shot parser retains only approved lost-C fix. Both Important findings addressed, no remaining Important/Critical findings in stage scope. Implementer evidence: focused RED 7 failed/47 passed, GREEN 54 rules; full suite 138 passed in 4.65s. No redundant rerun. Task 2 approved.
