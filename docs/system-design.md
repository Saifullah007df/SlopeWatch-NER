# SlopeWatch NER system design

## Purpose
A local research and teaching workbench for rainfall-triggered landslide assessment across representative North Eastern India locations. It demonstrates ingestion, evidence quality, ML inference, review episodes and outcome capture. It is not an operational public early-warning service, an evacuation trigger or an official hazard bulletin.

## Research corrections
NASA LHASA, GSI regional forecasts and Amrita sensor networks already provide related capabilities. Data fusion, ML and early warning are not new in themselves. This implementation targets a smaller reproducible workflow with explicit provenance, withheld scores for incomplete/stale observations and auditable human review. No invention or superior prediction accuracy is claimed.

## Architecture
Browser console → bounded same-origin FastAPI API → transactional SQLite repository → quality gate → versioned Random Forest inference → assessment history → episode state machine → reviewed local notification simulation and outcome records.

A separate training pipeline reads labelled CSV, validates the feature schema, partitions by group, evaluates against a prevalence baseline, and exports trees to plain JSON. No pickle or joblib model loading is accepted. A model registry separates candidate artifacts from the active model. The initial active model is trained on synthetic fixtures and its output is labelled a synthetic model score, never a calibrated landslide probability.

## Modules and boundaries
- schemas: explicit units, range limits and timezone-aware timestamps.
- models: deterministic synthetic generation, grouped holdout evaluation, forest JSON export/inference and controlled activation.
- engine: provenance checks, freshness/missingness gating, feature evidence and episode transitions.
- store: atomic observation/assessment/episode updates and audit records.
- API: observation import, zone and assessment views, scenarios, review and simulated delivery, outcomes and model operations.
- web: geographic point map, station workspace, evidence timeline, alert review, model laboratory and comparable-system references.

## Data strategy
Eight city-area demonstration points are illustrative, not instrumented field slopes. Coordinates are representative; slope and elevation are fixture values, not DEM-derived measurements. Each observation carries its own source, timestamp, missing fields and assessment/model lineage. The included 3/24/72-hour rainfall totals are supplied totals, not derived from a real rain-gauge stream.

Real-use research requires surveyed terrain, documented sensors, quality controls, event inventory and representative non-event exposure periods. User-uploaded CSV remains user-supplied and unverified. Relabelling synthetic data as real is not validation. Satellite imagery, IMD feeds, NASA products and actual IoT devices are not integrated in this build.

## Quality gates
Required dynamic features: rainfall over 3, 24 and 72 hours, volumetric soil-moisture fraction and deformation rate. Required static features: slope and elevation. Missing data, readings older than 60 minutes, materially future timestamps or values outside documented bounds do not become low-risk readings. The assessment is Unknown and no score is shown. Existing episodes are retained during loss of evidence.

## Episode policy
Demonstration bands: Low < 0.30; Moderate < 0.60; High < 0.85; Critical otherwise. These thresholds are uncalibrated project settings. Two consecutive quality-passed High/Critical observations open a review episode; Critical observations can escalate an existing episode. Two consecutive readings below 0.45 resolve its environmental condition. Moderate/high transitions reset that clearance streak. Unknown resets streaks and never resolves an episode. Each unique observation contributes at most once. Acknowledgement and closure are separate; closure requires resolved conditions, acknowledgement and a note.

No alert is automatically sent to people. An acknowledged active episode can queue a local notification rehearsal; dispatch simulates delivery or failure, with persistent attempts and a three-attempt limit. Every UI and export distinguishes simulated delivery from a real message. No SMS, email or push credentials are accepted by this version.

## Model governance
Random Forest is a baseline, not an assumption of fitness. GroupShuffleSplit keeps identical site/storm groups out of both training and holdout partitions; it does not establish temporal transferability. Metrics include event prevalence, precision, recall, F1, ROC AUC, Brier score and a prevalence baseline. Synthetic metrics only validate the software exercise. Uploaded models are never executed; artifacts are generated locally from bounded CSV. Activating a candidate is an explicit research action, not continuous automatic retraining.

Outcomes can be landslide, no landslide or uncertain. An uncertain or absent outcome is never converted into a negative label. Feedback is retained for expert curation and is not automatically recycled into training.

## Deployment and scale
Single trusted user, loopback-only, no shared-account identity claims. Same-origin mutations, Host checks and request bounds reduce browser abuse. SQLite transactions and guarded state transitions coordinate local work. A public service needs authentication, field validation, monitoring, delivery-provider integration and institution-approved operating procedures. Cloud autoscaling, cross-hazard reuse and region-wide validation remain future work.

## Delivery plan
1. Compare existing systems and revise claims.
2. Implement quality/provenance contracts and ML pipeline.
3. Build transactional ingestion and review episodes.
4. Add geographic dashboard, evidence views and model lab.
5. Exercise data-quality faults, duplicate requests, training and review workflows.
6. Publish source and tests to a separate public repository with no collaborators, matching the owner's repository-access preference.
