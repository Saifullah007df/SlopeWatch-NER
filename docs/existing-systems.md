# Comparable systems and design implications
Reviewed 17 October 2026. This is a focused comparison of related systems, not an exhaustive novelty or patent search.

| Existing system | Relevant capability | Implication for this project |
| --- | --- | --- |
| NASA LHASA | ML-based regional/global hazard estimates combining rainfall, soil moisture and terrain-related information; open source available | Do not claim that data fusion, ML hazard maps or source code are absent from existing systems. Respect the difference between broad situational awareness and a local warning service. |
| GSI National Landslide Forecasting Centre, Bhusanket and Bhooskhalan | Regional forecasting and dissemination, with inventory feedback and agency coordination | Present the project as a research complement, not a replacement for official advisories. Verify district coverage before making operational claims. |
| Amrita landslide monitoring | Instrumented monitoring using rain, soil-moisture, inclination and pore-pressure sensors, including a Sikkim deployment | Sensor fusion and North Eastern deployments already exist. New value must be demonstrated through evaluation and integration quality. |

## What changes from the presentation
The claims that there is no ML scoring, no data fusion or only manual warning are too broad. Remove them. The stated regional ranking is not established by the supplied slides and is not repeated. Avoid guaranteed warning lead time, lives-saved claims or cost savings without supporting evaluation.

The redesigned build makes freshness, provenance, model lineage and human review visible. These are engineering choices and a useful academic scope; this review does not establish their novelty.

## Sources
1. NASA, Machine Learning Model Doubles Accuracy of Global Landslide Nowcasts: https://www.nasa.gov/missions/gpm/machine-learning-model-doubles-accuracy-of-global-landslide-nowcasts/
2. NASA LHASA repository: https://github.com/nasa/LHASA
3. GSI, About NLFC: https://bhusanket.gsi.gov.in/about.html
4. Press Information Bureau, NLFC inauguration, 19 July 2024: https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=2034433&lang=2&reg=48
5. Amrita, Landslide Early Warning System: https://www.amrita.edu/project/landslide-early-warning-system/

The implementation does not copy these systems' models, ingest their outputs or imply agency endorsement.
