# Validation record

## Automated verification

Validated on Python 3.12 with the pinned dependency set: **38 tests passed**. JavaScript syntax and shell syntax are checked separately. CI runs the same suite on Python 3.12 and 3.13.

Tests cover input bounds and units, missing and stale evidence, chronological ingestion, duplicate idempotency, atomic batch rollback, repeated-reading episode opening and clearance, stale closure rejection, notification simulation retries and persistence, model activation and history lineage, immutable outcomes, CSV contracts, grouped holdout separation, JSON forest parity, API origin/host guards, and static UI contracts.

A dependency deprecation warning from the FastAPI/Starlette test client using httpx is recorded; it does not fail the suite.

## Reproducible synthetic evaluation

See [synthetic evaluation](synthetic-evaluation.json). Generate the same fixture with `python -m slopewatch example-training --output /tmp/training.csv`, then use the CLI training command documented in the README. Timestamps vary; fixture data, split and forest random seeds are fixed. The report includes independent group lists, confusion matrix, baseline Brier score and exported-tree parity.

These metrics describe synthetic labels sampled from a specified formula. They are not evidence of real landslide forecasting performance. Synthetic groups are software fixtures, not independent measured storms. User datasets require independently curated site/storm groups and field verification; the application cannot establish that independence from group names alone.

## Remaining validation and integrations

Visual browser interaction testing was unavailable in the development environment. Static HTML/JavaScript contracts and API workflows passed, but responsive layout, keyboard usability and complete browser journeys still require manual review.

Real sensor reliability, surveyed terrain, field-labelled events, time-separated and site-separated external validation, calibration, uncertainty, false alarm burden and lead time have not been measured. No live rainfall, satellite or IoT adapter, real notification provider, mobile application, production authentication or institutional warning process is connected. The current release is a local research workbench and notification rehearsal.
