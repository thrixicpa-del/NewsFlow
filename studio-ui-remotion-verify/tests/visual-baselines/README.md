# Workstation visual baselines

`approved/` contains only screenshots taken from NewsFlow's disposable visual-fixture renderer. They are regression-test assets, not production screenshots or user data, and are stored with Git LFS.

The capture harness always writes current screenshots and its result manifest to the ignored `.artifacts/workstation-visual-baselines/` directory. It reads approved references from this directory so a clean checkout can compare the same matrix.

Update an approved reference only after a reviewed intentional visual change, using the explicit `NEWSFLOW_UPDATE_VISUAL_BASELINES=1` flag on an isolated test run. Never create or update a baseline against production storage.
