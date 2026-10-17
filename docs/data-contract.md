# Data and model contract
All changes are local research actions. Times require UTC Z or an explicit offset and are normalized to UTC. More than five minutes ahead is rejected; smaller clock skew is tolerated. Current evidence expires after 60 minutes. GET views never count toward episode streaks.

## Features and units
- rain_3h_mm: preceding 3-hour total, 0–1000 mm.
- rain_24h_mm: preceding 24-hour total, 0–2000 mm.
- rain_72h_mm: preceding 72-hour total, 0–4000 mm.
- soil_moisture: volumetric fraction, 0–1. Convert percentages before import.
- slope_deg: static slope angle, 0–85 degrees.
- elevation_m: static elevation, 0–9000 metres.
- deformation_mm_day: nonnegative displacement-rate magnitude, 0–100 mm/day.

3h <= 24h <= 72h must hold. These are software input bounds, not hazard thresholds. Empty dynamic fields withhold inference; there is no zero imputation.

## Observation CSV
Exact header: zone_id,observed_at,source,rain_3h_mm,rain_24h_mm,rain_72h_mm,soil_moisture,deformation_mm_day,note

Sources: synthetic, manual-unverified or sensor-import-unverified. At most 300 rows, committed atomically. Import chronologically per zone. Identical zone/timestamp/payload retries return the original assessment; changed payloads conflict. Out-of-order readings are rejected.

## Training CSV
Exact header: rain_3h_mm,rain_24h_mm,rain_72h_mm,soil_moisture,slope_deg,elevation_m,deformation_mm_day,event_24h,group_id

100–5000 complete rows, five or more independent groups, labels 0 and 1. Missing/uncertain labels cannot train. Group correlated observations by site/storm. Exact duplicate feature rows are rejected. GroupShuffleSplit holds out 25% of groups with seed 42. Both partitions must contain both classes. This is not chronological or geographic transfer validation; group declarations are not independently verified.

The initial synthetic labels are sampled from a fixed logistic function of rainfall, moisture, slope and deformation. Metrics measure recovery of that invented relationship, not real landslide accuracy. Uploaded datasets remain unverified, including a re-uploaded synthetic example.

Random Forest: 60 trees, maximum depth 7, minimum four samples per leaf, seed 42, one CPU worker. Held-out metrics include precision, recall, F1 at score 0.5, ROC AUC, Brier score and a training-prevalence Brier baseline. Exported JSON retains the model fit on training groups; holdout groups are not used for fitting. No automatic feedback retraining occurs.

## Explanations
Forest impurity importance is global and can be biased. Local drivers replace one feature with its training median; the score difference is a sensitivity check, not SHAP or causal attribution. Substitutions can create implausible correlated feature combinations. Out-of-training-range features are flagged but inference is not calibrated or validated.

## Review and feedback
Bands are uncalibrated project settings: Low < 0.30, Moderate < 0.60, High < 0.85, Critical otherwise. Two distinct High/Critical observations open a review episode. Unknown resets streaks and never clears an episode. Gaps over 60 minutes also reset streaks. Two consecutive readings below 0.45 resolve the condition; subsequent score >= 0.45 or Unknown removes clearance. Closure requires acknowledgement, current valid clearance and a note. Model activation resets streaks and applies only to new observations.

Acknowledgement records local-user, not an authenticated authority. Outcomes are one immutable record per episode, not automatically training eligible. Uncertain is not a negative label.

Notification records explicitly say simulation; retries survive restart and stop after three failures. Dispatch cancels records when review, severity, condition or freshness no longer qualifies. No messaging provider is called.
