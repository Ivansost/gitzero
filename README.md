# GitZero

GitZero is an explainable Python CLI that scans a GitHub repository URL or local
repository folder for signals consistent with AI-assisted code.

It is designed for careful review, not accusations. GitZero does **not** prove authorship.
It surfaces evidence, ranks the strongest signals, and explains why a repository may deserve
closer inspection.

[Introduction](#introduction) |
[How It Works](#how-it-works) |
[Install](#install) |
[Usage](#usage) |
[Evaluation](#evaluation) |
[Demo](#demo)

## Introduction

AI-generated and AI-assisted code often leaves patterns across commit history, project shape,
documentation style, and static code structure. GitZero combines those signals into an
explainable terminal report.

The project was built as a data, software, and AI systems portfolio piece:

- **Data pipeline:** batch scanning, labeled corpus export, feature columns, and model-ready
  JSONL/CSV output.
- **Software engineering:** Typer CLI, Rich terminal UI, test coverage, linting, local and
  GitHub URL support, and safe temporary clone cleanup.
- **AI evaluation:** heuristic scoring plus an optional experimental ML model for calibration.
- **Responsible language:** risk bands are triage labels, not authorship claims.

### Screenshot Slots

Use these slots for screenshots before publishing the README:

| Slot | What to capture | Suggested file |
| --- | --- | --- |
| CLI summary | A normal `gitzero scan <repo>` report showing the summary and signal map. | `docs/images/scan-summary.png` |
| Hard evidence | A scan where GitZero finds an AI config file or explicit README phrase. | `docs/images/hard-evidence.png` |
| JSON output | A terminal/editor view of `gitzero scan <repo> --json`. | `docs/images/json-output.png` |
| Batch workflow | A corpus scan or evaluation output. | `docs/images/batch-evaluation.png` |

After adding images, place them near the relevant sections, for example:

```md
![GitZero scan summary](docs/images/scan-summary.png)
```

## How It Works

GitZero runs a multi-stage scan:

1. **Load the repository**
   - Accepts a local folder, public GitHub URL, or public git URL.
   - URL scans are cloned into a temporary directory and deleted after the scan.

2. **Analyze git history**
   - Looks for large commit bursts, file creation waves, short project timelines,
     single/drop-style histories, no-merge histories, formulaic commit messages,
     author uniformity, and unusual time clustering.

3. **Analyze source files**
   - Uses Python `ast`, regex heuristics, and `radon` complexity metrics.
   - Supports Python, JavaScript, TypeScript, JSX/TSX, notebooks, and common source files.
   - Ignores common generated files, lockfiles, vendor libraries, framework config files,
     build output, caches, virtual environments, and oversized files.

4. **Detect hard evidence**
   - Flags explicit AI-assistant project files such as `AGENTS.md`, `CLAUDE.md`,
     `.cursorrules`, Copilot instructions, `.aider`, `.continue`, Windsurf/Cline/Roo rules,
     and README phrases like `built with ChatGPT`, `made with Cursor`, or
     `built with help from ChatGPT`.

5. **Apply false-positive dampeners**
   - Reduces risk when the repo shows organic development patterns: long-lived history,
     multiple authors, merge commits, debug residue, personal TODOs, substantive tests,
     README/code alignment, used dependencies, and starter-template patterns.

6. **Explain the result**
   - Prints a risk band, confidence score, top signals, highest-signal files, skipped-file
     counts, and optional verbose per-file findings.

## Install

GitZero is a Python package with a CLI entrypoint named `gitzero`.

### Recommended: install from GitHub with pipx

[`pipx`](https://pipx.pypa.io/stable/) installs CLI tools into isolated environments.

```bash
pipx install git+https://github.com/Ivansost/gitzero.git
```

Then run:

```bash
gitzero help
```

### Install with pip

```bash
python -m pip install git+https://github.com/Ivansost/gitzero.git
```

### Local development install

```bash
git clone https://github.com/Ivansost/gitzero.git
cd gitzero
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,ml,parsing]"
```

Run the local CLI:

```bash
.venv/bin/gitzero help
```

## Usage

Scan a public GitHub repository:

```bash
gitzero scan https://github.com/user/project
```

Scan a local repository:

```bash
gitzero scan ./my-local-repo
```

Print machine-readable JSON:

```bash
gitzero scan ./my-local-repo --json
```

Show every per-file signal:

```bash
gitzero scan ./my-local-repo --verbose
```

Skip git history and score only the current source tree:

```bash
gitzero scan ./my-local-repo --no-git-history
```

Exclude folders or globs:

```bash
gitzero scan ./my-local-repo --exclude node_modules --exclude dist
```

Use the optional experimental ML model:

```bash
gitzero scan ./my-local-repo --ml-model ./model.joblib
```

`--ml-model` is experimental. Use the probability as a calibration aid next to the
heuristic score, not as a standalone authorship claim.

### Risk Bands

| Band | Range | Meaning |
| --- | --- | --- |
| Low | 0-39 | Few signals consistent with AI-assisted code. |
| Medium | 40-69 | Several signals are elevated. Review the top findings. This is not an AI claim. |
| High | 70-100 | Many signals are elevated. Inspect history and files closely. |

## Batch And Corpus Workflow

Create a labeled fixture corpus:

```bash
gitzero fixtures ./fixtures/gitzero-corpus
```

Scan a labeled corpus into JSONL:

```bash
gitzero batch ./fixtures/gitzero-corpus \
  --labels ./fixtures/gitzero-corpus/labels.csv \
  --format jsonl \
  --output ./fixtures/results.jsonl
```

Scan a two-level corpus layout:

```text
corpus/
  ai_generated/repo-a
  ai_assisted/repo-b
  human/repo-c
  template/repo-d
```

```bash
gitzero batch ./corpus --recursive --label-from-parent --format jsonl -o corpus.jsonl
```

Batch rows include inspection fields and ML-ready feature columns:

```text
signal.git.large_commits_present
signal.git.large_commits_score
signal.git.large_commits_weight
signal.dampener.git.multi_author_history_score
signal.dampener.static.personal_todo_patterns_score
```

## Evaluation

GitZero currently uses heuristic scoring as the primary product behavior. The ML model is
kept optional because the live tests showed the heuristic is more reliable for public scans.

Current validation artifacts:

- **Cleaned labeled corpus:** 129 repositories across `ai_generated`, `ai_assisted`,
  `human`, and `template`.
- **Grouped cross-validation:** grouped by repository owner to reduce leakage.
- **Ablation model without hard evidence:** ROC-AUC `0.903`, PR-AUC `0.853`.
- **Live out-of-corpus smoke test:** 60 GitHub repositories.
  - Hard-evidence AI: 17/20 scored High.
  - Human OSS: 0/20 scored High.
  - AI-assisted candidates: mostly Medium/High, with intentionally conservative ML scores.

The main takeaway: GitZero is useful as an explainable review tool. It should not be framed
as a definitive detector.

## Tech Stack

- [Python](https://www.python.org/) package with a `gitzero` console script.
- [Typer](https://typer.tiangolo.com/) for CLI commands.
- [Rich](https://rich.readthedocs.io/) for terminal UI.
- [PyDriller](https://pydriller.readthedocs.io/) plus git fallback for history analysis.
- [radon](https://radon.readthedocs.io/) for complexity metrics.
- Optional [scikit-learn](https://scikit-learn.org/) / [joblib](https://joblib.readthedocs.io/)
  model loading for experimental ML probability.

## Development

```bash
python -m pip install -e ".[dev,ml,parsing]"
python -m pytest
python -m ruff check .
```

## Demo

Full demo, screenshots, and technical write-up:

[GitZero project write-up and demo](https://your-website.com/gitzero)

Replace the demo link with your portfolio URL after publishing the write-up.
