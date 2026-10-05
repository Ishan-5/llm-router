# Customer-support difficulty model - held-out SUPPORT evaluation

> **Superseded - do not quote these numbers.** This report scores the
> `support_all` / `support_ds3` exploratory variants, which are not the models
> the router serves. `feature_builder.py` loads `support_final_3tier.joblib`
> (lisa) and `support_final_2tier.joblib` (kate). Current shipped numbers:
> lisa MAE 0.822 / Spearman 0.786 / frontier recall 80.4% / escape 19.6%;
> kate MAE 0.822 / Spearman 0.786 / frontier recall 86.0% / escape 14.0%.
> See `customer-support/README.md` for those and this file's own caveats
> (label noise, unlabeled batches) still apply.

Split is by batch (60/14/14) so near-duplicate tickets cannot leak across the boundary. Thresholds calibrated on the calib batches only.

## Test-batch results (support tickets only)

| model | thresholds | MAE | Spearman | tier acc | frontier recall | under-routed |
|---|---|---|---|---|---|---|
| support_all | deployed 4.5/6.0 | 0.740 | 0.861 | 79.2% | 28.2% | 395/550 |
| support_all | calibrated 6.5/7.0 | 0.740 | 0.861 | 92.5% | 5.1% | 186/196 |
| support_ds3 | calibrated 6.5/7.0 | 0.911 | 0.728 | 86.4% | 4.8% | 177/186 |
| *generic (secondary)* | deployed 4.5/6.0 | 1.301 | 0.757 | 68.3% | 25.5% | 410/550 |

## Per-tier recall on test support tickets

- **support_all (calibrated)**: cheap 99.0% (n=2604)   frontier 5.1% (n=196)
- **support_ds3 (calibrated)**: cheap 98.1% (n=1304)   frontier 4.8% (n=186)
- **generic (secondary)**: cheap 81.0% (n=2019)   mid 59.3% (n=231)   frontier 25.5% (n=550)

## Score distribution on test support tickets

gold mean 2.94   predicted mean 3.11

| gold score | rows | model predicts (mean) |
|---|---|---|
| 0 | 117 | 1.19 |
| 1 | 1,006 | 1.62 |
| 2 | 375 | 2.31 |
| 3 | 306 | 3.34 |
| 4 | 215 | 3.96 |
| 5 | 231 | 5.00 |
| 6 | 354 | 5.50 |
| 7 | 161 | 5.43 |
| 8 | 32 | 6.12 |
| 9 | 3 | 6.57 |

## Hardest test tickets (the 'system design in a support chatbot' risk)

| gold | pred | tier | query |
|---|---|---|---|
| 9 | 6.83 | frontier | Investigation Needed for Suspected Medical Data Breach  To the support team, a m |
| 9 | 7.06 | frontier | Severe Service Disruption Detected in EMR Platform  Dear Support Team,\n\nWe hav |
| 9 | 5.82 | mid | Critical Service Disruption  Dear Customer Support Team,\n\nI urgently seek imme |
| 8 | 6.44 | frontier | Regarding the report on the data breach in the hospital's system where sensitive |
| 8 | 6.08 | frontier | Several Critical Devices Experiencing Network Failures  Dear Support Team,\n\nWe |
| 8 | 5.59 | mid | Critical Service Outage  Dear IT Services Support Team, I am writing to notify y |
| 8 | 3.62 | cheap | Enhancing Investment Algorithm Efficiency Daily Assistance  Greeting from custom |
| 8 | 6.32 | frontier | Medical Data Encryption Issue  Hello customer support, we are experiencing a pro |
| 8 | 6.03 | frontier | Support Request for Data Breach in Healthcare Systems  A data breach has been de |
| 8 | 6.24 | frontier | Critical Alert: Automated Portfolio Rebalancing System Failure  Dear Customer Su |
| 8 | 6.35 | frontier | Alert for Data Breach  A data breach has been detected in the healthcare provide |
| 8 | 6.20 | frontier | Emergency Support Required  An unauthorized access attempt was detected in the m |
| 8 | 7.04 | frontier | Potential Data Breach in Medical Records System  There is a potential data breac |
| 8 | 5.80 | mid | Notification of Data Access Issue  Customer support reports that a healthcare pr |
| 8 | 6.56 | frontier | Hospital Network Security Concerns  Customer support has documented an incident  |

## Reading this

- Spearman and tier accuracy on these rows are the support model's real numbers. No cross-domain comparison is involved or meaningful.
- The calibrated thresholds matter more than the model here: 4.5/6.0 were tuned on generic data, and the support score distribution is shifted well below it.
- `support_ds3` vs `support_all` on the same split answers whether the DS2 synthetic rows help or dilute, on the data that actually matters.
- Label noise sets a floor on MAE: an independent second labeler disagreed with Claude on 68% of 1,000 tickets (mean abs diff 1.34), so MAE below ~1.0 on this data is not attainable and should not be a target.

## Not done

- 2 of 90 reply files were rejected (batch_225 gave 209 lines, batch_238 gave 199), so 400 of 18,000 labels are missing.
- The remaining 148 batches are unlabeled. Whether to finish them is a separate call; this report does not assume it.
