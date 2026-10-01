# Generated same-path replacement chain — Astra review

Independent core review found a P2: valid two/three-step JPEG replacement plans stopped at the second action because the shared batch source reservation treated the committed historical subject as another selected input.

Reviewed the narrow generated.py exception and all 19 new regressions. Every overlapping source must be strictly earlier in this batch, a committed same-path conversion with committed owned replace record, and part of the complete backward Fingerprint chain ending at the current expected source. Current ticket and held-source validation remain unchanged. Other selected inputs, cross-path histories, failed/prepared operations, missing ownership and broken identities still reject before mutation. Planner scope is unchanged.

Director verification: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_generated.py tests/test_automation_runtime.py -q --basetemp=sandbox/astra020-chain-review` — **147 passed in 18.01s**. Real direct and runtime two/three-step execution and inverse undo restore initial bytes, ADS, creation and modification times. Negative cases include a new external file identity despite identical bytes/times, both before and after ticket issuance.

No open Critical/Important finding in this delta. Root independent delta review and owned cross-volume evidence remain separate final checks. No full suite, installed-app mutation, or package acceptance claimed here.
