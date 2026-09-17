# GitZero

A CLI tool that scans any GitHub repository for signals consistent with AI-generated or AI-assisted code. Analyzes 25+ behavioral and static signals across git history and source files, outputs an explainable risk report, and includes a full ML training pipeline.

→ **[Full project writeup and demo](https://www.ivansostaric.com/projects/gitzero)**

---

![GitZero scan output](https://raw.githubusercontent.com/Ivansost/gitzero/main/photos/mainreport.png)

---

## How It Works

GitZero uses a hybrid detection pipeline: deterministic heuristics produce the primary explainable score, while an optional calibrated Random Forest provides a separate learned probability.

![GitZero architecture and machine-learning pipeline](https://raw.githubusercontent.com/Ivansost/gitzero/main/photos/gitzero-architecture-dark.png)

1. **Load and filter the repository.** GitZero accepts a local folder or public GitHub URL, builds a source-file index, and excludes dependencies, generated code, vendored libraries, caches, training artifacts, and framework scaffolding.
2. **Analyze two evidence families.** Git history analysis measures repository behavior over time, while static analysis examines patterns in the current source code.
3. **Normalize and score the evidence.** Findings use a common signal format containing a score, supporting details, affected files, and confidence context. The heuristic combines independent signal families and applies false-positive dampeners.
4. **Produce an explainable report.** The CLI shows the risk score, Low/Medium/High band, confidence, dampening, top signals, highest-signal files, and signal map. ML predictions and detailed JSON remain available through the research tools.

### Why Use an ML Model?

The Random Forest is an **optional second opinion**, not a replacement for the explainable heuristic. Its purpose is to learn nonlinear interactions between weak signals that fixed weights may miss.

- It trains on raw signal and scan-metadata features, not GitZero's final `risk_score`.
- Hard-evidence columns are excluded so the model must learn subtler repository patterns.
- Its probability is reported separately and never overwrites the heuristic result.
- A disagreement between the two methods indicates uncertainty and gives the reviewer a reason to inspect the evidence.

The current calibrated Random Forest was evaluated with owner-grouped 5-fold cross-validation on 193 labeled repositories and reached **0.968 ROC-AUC** on that corpus. This is a project benchmark, not a claim of universal authorship-detection accuracy.

---

## What It Detects

**Git signals** — large commit bursts, file creation waves, single-drop histories, no-merge linear histories, formulaic commit messages, author uniformity, tight commit time clustering.

**Static signals** — naming entropy, docstring density, type annotation coverage, complexity uniformity, structural repetition, debug artifact absence, generic TODOs, shallow test quality, README-to-code misalignment.

**Hard evidence** — explicit AI config files: `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.aider`, Copilot instructions, and README phrases like `vibe coded` or `built with ChatGPT`.

**False-positive guards** — vendor libraries (jQuery, Bootstrap), framework scaffolding, multi-author history, merge commits, and long-lived organic repos all reduce the score automatically.

---

## Highlights

- 25+ detection signals with per-signal weights and confidence scoring
- Jupyter notebook support — extracts and analyzes `.ipynb` code cells
- ML pipeline: Random Forest with grouped cross-validation on 193 labeled repos — **0.968 ROC-AUC** without hard-evidence features ([evaluation summary](https://github.com/Ivansost/gitzero/blob/main/corpus/_prep/corpus_summary_v7.md))
- Batch export to JSONL/CSV with ML-ready feature columns for every signal
- Separate research tools for training and experimental ML predictions
- 50+ tests, ruff clean

---

## Install

```bash
pip install gitzero
```

## Usage

```bash
gitzero scan https://github.com/user/repo     # scan any public GitHub repo
gitzero scan ./my-local-repo                 # scan a local folder
gitzero help                                 # show basic usage
```

The public CLI has only `scan` and `help`, with no scan options. Scans include Git
history and supported source files, automatically exclude generated/dependency
folders, and use limits of 2,000 source files and 400 KB per file.

## ML research workflow

Install the project and research dependencies from this checkout:

```bash
python -m pip install -e '.[ml,dev]'
```

Keep labeled repositories under `corpus/<label>/<repository>`. Supported training
labels are `human`, `template`, `ai_assisted`, and `ai_generated`. Export features
and train the model with development scripts, separate from the public CLI:

```bash
python scripts/export_features.py corpus corpus/_prep/features.jsonl
python scripts/train_baseline.py --input corpus/_prep/features.jsonl --report-output corpus/_prep/baseline_report.txt --save-model corpus/_prep/model.joblib
python scripts/accuracy_audit.py --ml-model corpus/_prep/model.joblib --skip-corpus --skip-live
```

The last command scans the current folder and saves detailed JSON, including ML
probability, under `/tmp/gitzero_accuracy_audit`. Omit the skip flags to also audit
the corpus and the script's public-repository examples. Only load model artifacts
you trust. Feature export also supports `--labels labels.csv` and `--format csv`.

The detector and feature definitions are shared by the CLI and research tools;
ML never overwrites the heuristic score. Existing benchmark results describe the
recorded V7 corpus, not a new evaluation of every subsequent checkout.

## Code walkthrough

The CLI loads the repository, runs Git and static analysis with progress feedback,
combines the findings in the scorer, and renders the original Rich report.
`scanner.py` provides the same detector sequence for the research scripts. `models.py`
defines their shared data structures. For ML, `evaluation.py` builds feature rows,
`scripts/train_baseline.py` trains and evaluates models, and `ml.py` runs inference.
The fixture generator remains an internal testing helper.

---

**Stack:** Python · Typer · Rich · PyDriller · radon
