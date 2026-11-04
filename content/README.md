# Content

Scenario-as-code (docs/PLAN.md §11). Phase 3 adds the first base app (ShopKart), fault modules
and three scenarios.

- `base-apps/`: realistic systems that scenarios break
- `faults/`: reusable, parameterised fault modules with symptom contracts
- `scenarios/<track>/<slug>/`: scenario.yaml, inject/, verify/, hints.md, solution/, approaches/, rubric.yaml, case-file/
- `scenarios/<track>/<slug>/case-file/`: the free, sandbox-less format (ADR 018). `case.yaml` holds the three questions, the commands to capture and the clues. `evidence.json` is a recording of a real run: regenerate it with `devgrill-content record <slug>`, never by hand
- `quickfire/`: Quick Fire card decks
