# Independent FileHub 0.2.2 delta review

No blocking finding in the reviewed product-source/test delta against `cd86abeb484c08aa21ad44211ed339356259c5d1`, frozen as `681bc6965617f7791bf22635b7045f36c15689c5`.

Scope: conversion-only collision numbering; removal of the two settings day-control arrows; thin rounded scrollbar styling. Read the complete changed source and focused tests, plus the existing runner, path validation and naming validation surrounding the change. Product files and Git index were not modified.

The allocator leaves an available name unchanged, advances only a final hyphen-number suffix past the occupied same-extension family maximum, preserves source padding/spelling, and folds both family and occupied names consistently (including the Straße regression). Files/directories and selected/batch/intermediate paths reserve names. Same-path own replacement remains exempt; other input paths remain reserved. Rule reservations commit only on a complete valid plan; standalone reservations commit after successful inspection, so failed decoding does not consume an output name. Existing rule preview inspects before planning.

Execution binds the allocated preview path and retains late-occupancy refusal and existing no-clobber publication. Cross-extension replacement continues through the original private-backup/undo path; keep mode retains its original. Reviewed focused tests exercise both standalone and rule execution, true same-path replacement, numbered backup and undo, virtual intermediate replacement, occupied-output preservation, duplicate input rejection, reservation rollback and late occupancy. The two added real executable self-test checks actually encode/read images, inspect the journal backup, undo and verify original/occupied bytes, and create a late occupant to verify no silent reallocation.

UI source changes are narrow: `NoButtons` is set only on the two settings day controls, retaining range/suffix/save behavior; conversion quality buttons remain. Scrollbar stylesheet specifies 8 px dimensions, 4 px rounding, zero-size end controls and explicit footer specificity. Directly inspected the native dark-settings DPR 1 and dark-conversion DPR 2 images: thin rounded no-arrow scrollbars are visible and quality arrows remain. These are owned-window captures, not an installed-app test.

Evidence boundary: independently reviewed code, focused test logic, and recorded backend GREEN (94 passed in 10.68 s) and UI evidence (26 passed in 2.59 s plus native interactions). Did not duplicate the suite, run an additional probe, or review packaging binaries. Root's fresh full suite and packaged acceptance remain separate release gates. No live installation, registry, real user state, environment dependencies, or process state was changed.

Reviewed file SHA-256 values:

```text
27141bd69329ca102ec09ecd27e7eb99314613aeec8b82437a6c9b57526aee54  src/filehub/conversion/naming.py
a6bd925ede5f4d8ec693756f99bf7c4de13143f9f8cdd657ae2b2812bead09b3  src/filehub/automation/executor.py
4c2e2ead23771c5d84ed3979f420b48d1659b0762ecf74de795f5561f8f345c5  src/filehub/automation/planner.py
c228fd9108f40e1dcfc2abe57bc6f0d4da79e6c2036da8af31389973455a3c30  src/filehub/selftest020.py
862c02d5cbc69b0055a349d69cf159404b646223cc12ea2740a424c7a6b84a88  src/filehub/ui/action_editor.py
35fa4d60521c2093495c65d706699260df2750f776ad83b064bc2080ebc37da9  src/filehub/ui/main_window.py
9c5afb0a1dcd961ed81b7be74ae1b1c3d75e92c755f283bcef8387bea1645ae6  src/filehub/ui/theme.py
c1933806dca9f1be1c9ddd945e07afb3441ef423166cc5c17a34b91dda557b33  tests/test_conversion_numbering.py
86e4dea74fed41c87329d5586c1e0cac8212f65380a2372a67a2106c9f4ff8aa  tests/test_conversion_numbering_runtime.py
90784dab314a3f7645c7fb5ee7d5f40fc2278df10e3f56ad957e426d604f22f2  tests/test_automation_planner.py
fb10ccbb160ed8c32352f904bf815ee537328432a8dcfe3bb0b6fd8085a57544  tests/test_automation_runtime.py
61be4e3acf2c07c07297529bd7cf483ebbc678d3fb9661a115ef9d35dde1a9ad  tests/test_selftest020.py
```
