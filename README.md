# SlopeWatch NER

A local landslide **research workbench** for representative North Eastern India locations. It connects observations, quality checks, a Random Forest baseline, evidence views and reviewed notification rehearsals.

**The initial model and terrain are synthetic. Scores are not calibrated landslide probabilities. No public warning, evacuation advice, SMS, email or push message is issued.** Real field deployment needs documented sensors, surveyed terrain, labelled events, independent validation and institutional operating procedures.

## Run on your laptop

Requires Python 3.12+ and a browser. No frontend build or Node.js installation is needed to run.

```bash
git clone https://github.com/Saifullah007df/SlopeWatch-NER.git
cd SlopeWatch-NER
bash run.sh
```

Open **http://127.0.0.1:8000**. The first launch trains a deterministic synthetic baseline and seeds eight demonstration zones. Stop with Ctrl+C; rerun `bash run.sh`. State is retained in `runtime/workspace.sqlite3`. To change the port: `PORT=8001 bash run.sh`. To select a database, set `SLOPEWATCH_DB` before launch.

Manual installation:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -c requirements.lock
python -m uvicorn slopewatch.api:create_app --factory --host 127.0.0.1 --port 8000
```

## What is implemented

- Regional geographic point view, monitoring-zone directory, evidence history and one-feature sensitivity checks.
- Range, unit, missing-data, freshness, duplicate and out-of-order validation. Missing/stale evidence becomes **Unknown**, never Low.
- Transactional single and CSV batch ingestion, model/observation lineage and explicit source provenance.
- Review episodes after two High/Critical observations; acknowledgement, two-reading clearance and guarded closure.
- Local notification outbox with **simulation-only** delivery, bounded failure retries and persistence across restart.
- Outcome capture including uncertain; no automatic conversion into training labels.
- Candidate model training from bounded labelled CSV, grouped holdout metrics, baseline comparison and explicit activation.
- Plain JSON forest export and inference; no pickle/joblib loading of untrusted artifacts.
- Workspace JSON and GeoJSON exports; local audit events and API documentation at `/docs`.

## Demonstrate the workflow

1. Open a zone from the point map. Inspect the synthetic source, observation time, terrain fixture and score explanation.
2. Select **Intense storm** and add two new synthetic readings to a quiet zone. The two distinct observations open a review episode.
3. Open **Review episodes**, acknowledge with a note and queue a simulation.
4. Run the notification simulation, optionally injecting failure. The result says `simulated_delivered`, never real delivery. Three failures latch `failed`.
5. Add two **Quiet conditions** readings. Review and close the episode once clearance is valid.
6. Record an outcome. Choose **uncertain** when no verified field outcome exists.
7. In **Model laboratory**, download the explicitly synthetic CSV example or provide a curated dataset. Train a candidate, inspect its held-out metrics and activate it explicitly for research. New observations use the active model; historical records keep their original model.

Freshness expires after 60 minutes. Existing seed readings can become Unknown after the workspace has been running for a while. Add fresh synthetic observations to continue the demo. The pre-seeded Agartala and Itanagar examples intentionally show stale and missing evidence. Historical charts retain at-assessment-time scores; they are not current warnings.

## Training and data contracts

[Data contract](docs/data-contract.md) defines exact CSV headers and units. Downloads in the GUI provide templates. Training needs 100–5000 rows, at least five independent site/storm groups and both binary labels in training and holdout. User-supplied data remains unverified.

```bash
source .venv/bin/activate
python -m slopewatch example-training --output /tmp/synthetic-training.csv
python -m slopewatch train /tmp/synthetic-training.csv --output /tmp/research-forest.json
```

This CLI trains and exports a candidate; it does not activate it in the API's registry. The forest uses only training groups. Model reports include precision, recall, F1, ROC AUC, Brier score, a prevalence baseline and an export-parity check. Metrics on synthetic data only measure the software exercise. They do not establish real prediction accuracy or warning lead time.

## Research basis and redesigned scope

Related systems already exist, including NASA LHASA, GSI's regional forecasts and Amrita's instrumented monitoring in Sikkim. This project does not claim to invent data fusion, ML landslide scoring, GIS or alerts. See [comparable systems](docs/existing-systems.md), [system design](docs/system-design.md) and [validation](docs/validation.md).

The supplied slides propose real sensors, satellites, live forecasts and external messaging. **Those integrations are not implemented here.** This build provides explicit observation imports and a reproducible, working research pipeline. No IMD/NASA or satellite API, actual IoT hardware, mobile app or external delivery provider is connected. Geographic points and terrain are demonstration fixtures, not a measured hazard map.

## Project structure

- `slopewatch/schemas.py`: input contracts and units.
- `slopewatch/models.py`: synthetic generator, grouped training, JSON trees and inference.
- `slopewatch/engine.py`: evidence quality, assessment and episode/rehearsal workflows.
- `slopewatch/store.py`: SQLite transactions and local audit persistence.
- `slopewatch/api.py`: local API, CSV import, registry and exports.
- `web/`: offline-capable HTML/CSS/JS/SVG interface, no CDN dependencies.
- `tests/`: mathematical, workflow, model, API and static UI checks.

## Verification

```bash
python -m pip install -r requirements-dev.txt -c requirements.lock
python -m pytest -q
node --check web/app.js   # optional; requires Node.js
bash -n run.sh
```

CI repeats checks on Python 3.12 and 3.13. Browser visual/interaction testing was unavailable during development; that limit is recorded rather than claimed as passed.

## Access and privacy

Designed for one trusted user on loopback. No shared-user authentication or agency-approval identity is provided. Host and same-origin checks are enabled. Keep databases and sensitive imported data outside Git; local history is unencrypted. A host administrator can change the audit database, so it is not an immutable audit service.

Source is public for viewing and cloning; no collaborators are added. Others can modify their own forks, but cannot directly push to this repository without write access.

## Academic project attribution

Based on the supplied Artificial Intelligence Project Review 2: **AI-Based Early Warning and Landslide Risk Monitoring System in the North Eastern Region**. Team: Boopathi R, Yogaprasath N and Prabanjan T. The implementation redesign and supporting source comparison are documented in `docs/`.
