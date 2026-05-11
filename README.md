# GitZero

A CLI tool that scans any GitHub repository for signals consistent with AI-generated or AI-assisted code. Analyzes 25+ behavioral and static signals across git history and source files, outputs an explainable risk report, and includes a full ML training pipeline.

> GitZero surfaces evidence — it does not prove authorship.

→ **[Full project writeup and demo](https://your-website.com/gitzero)**

---

<!-- Screenshot: gitzero scan output -->
<!-- ![GitZero scan](docs/images/scan-summary.png) -->

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
- ML pipeline: Random Forest with grouped cross-validation on 129 labeled repos — **0.903 ROC-AUC** on ablation evaluation
- Batch export to JSONL/CSV with ML-ready feature columns for every signal
- `--ml-model` flag for experimental probability alongside the heuristic score
- 35+ tests, ruff clean

---

## Install

```bash
pip install gitzero
```

## Usage

```bash
gitzero scan https://github.com/user/repo     # scan any public GitHub repo
gitzero scan ./my-local-repo --verbose        # show per-file signal breakdown
gitzero scan ./my-local-repo --json           # machine-readable output
gitzero batch ./corpus --recursive --label-from-parent --format jsonl -o out.jsonl
```

---

**Stack:** Python · Typer · Rich · PyDriller · radon · scikit-learn
