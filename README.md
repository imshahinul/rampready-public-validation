# RampReady Public Validation

This directory is a staged candidate for a public, evidence-preserving
GitHub Actions validation job.

Its purpose is limited to the Phase 4R paired-source temporal diagnostic:

- USACE central `Boat Ramps`
- official USACE ArcGIS `Boat`
- 19 frozen Tier-A facilities
- no `AreaStatus` substitution
- no safety claim
- no transparent ArcGIS fallback authorization

The observation is currently **not activated**.

The intended persistence model follows the CampReady-style public-validation
pattern:

- append-only `history.jsonl`
- per-run evidence under `runs/`
- minimal continuity state under `state/`
- repository commits used to persist results across ephemeral GitHub runners

No scheduled workflow is present at this checkpoint.
