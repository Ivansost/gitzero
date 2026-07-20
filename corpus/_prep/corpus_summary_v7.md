# GitZero Corpus V7

## Dataset

| Label | Repositories | Unique owners | Explicit hard evidence |
|---|---:|---:|---:|
| AI generated | 50 | 50 | 43 |
| AI assisted | 50 | 50 | 19 |
| Human | 50 | 50 | 0 |
| Template | 43 | 43 | 0 |
| **Total** | **193** |  | **62** |

All repositories are valid Git repositories with at least one commit. GitHub repositories are full, non-shallow clones. The 60 repositories used in earlier live tests are excluded from this corpus.

AI labels require an explicit repository README declaration. Human repositories come from the previously verified corpus. Template repositories are unmodified outputs from official or local project generators.

## Heuristic Separation

| Label | Low | Medium | High | Average score |
|---|---:|---:|---:|---:|
| AI generated | 3 | 3 | 44 | 86.1 |
| AI assisted | 20 | 8 | 22 | 59.0 |
| Human | 50 | 0 | 0 | 27.7 |
| Template | 40 | 3 | 0 | 29.6 |

The public heuristic is intentionally conservative. AI-assisted repositories are often ambiguous because human development history and AI assistance can coexist. False-positive control is stronger: no human or template repository scored High.

## Grouped Cross-Validation

Hard-evidence feature columns are removed from these results. Repositories are grouped by owner so one author's style cannot appear in both training and validation folds.

| Model | ROC-AUC | PR-AUC | Brier score |
|---|---:|---:|---:|
| Random Forest | 0.968 | 0.979 | 0.066 |
| HistGradientBoosting | 0.971 | 0.981 | 0.068 |
| Logistic Regression | 0.938 | 0.953 | 0.122 |

The saved optional CLI model remains the Random Forest because its discrimination is effectively tied with HistGradientBoosting while its probability calibration is slightly better.

At a 0.70 Random Forest threshold:

- True positives: 82
- False positives: 0
- True negatives: 93
- False negatives: 18
- Precision: 1.000
- Recall: 0.820
- Accuracy: 0.907

## Files

- `corpus_manifest_v7.jsonl`: source URL and label evidence for every corpus repository
- `corpus_git_inventory_v7.jsonl`: Git validity, history depth, commit count, author count, and remote URL
- `corpus_features_v7.jsonl`: flattened GitZero training features
- `baseline_report_v7_random_forest.txt`: full grouped validation report and misclassifications
- `baseline_report_v7_logistic_regression.txt`: interpretable linear baseline
- `baseline_report_v7_hist_gradient_boosting.txt`: boosted-tree comparison
- `gitzero_baseline_ablation_v7.joblib`: optional no-hard-evidence Random Forest artifact
- `live_test_exclusions_v7.txt`: repositories kept out of training because they were used for live testing
