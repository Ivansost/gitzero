# GitZero

GitZero is a Python CLI that scans a GitHub repository URL or local repository folder for
signals consistent with AI-assisted code. It is designed as a portfolio-ready detector demo:
polished terminal output, explainable scoring, and careful language about uncertainty.

GitZero does not prove authorship. It reports behavioral and static signals that may deserve
closer review.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Usage

```bash
gitzero scan https://github.com/user/project
gitzero scan ./my-local-repo
gitzero batch ./repos --labels ./repos/labels.csv --format jsonl
gitzero batch ./corpus --recursive --label-from-parent --format csv -o corpus.csv
gitzero fixtures ./fixtures/gitzero-corpus
gitzero help
```

Useful flags:

```bash
gitzero scan ./repo --no-git-history
gitzero scan ./repo --exclude node_modules --exclude dist
gitzero scan ./repo --max-file-size 250
gitzero scan ./repo --max-files 1000
gitzero scan ./repo --verbose
gitzero scan ./repo --json
```

Batch/evaluation workflow:

```bash
gitzero fixtures ./fixtures/gitzero-corpus
gitzero batch ./fixtures/gitzero-corpus \
  --labels ./fixtures/gitzero-corpus/labels.csv \
  --format jsonl \
  --output ./fixtures/results.jsonl
```

For a two-level real corpus, either keep an explicit `labels.csv` for auditability or use
recursive parent labels:

```bash
corpus/
  ai/repo-a
  human/repo-b

gitzero batch ./corpus --recursive --label-from-parent --format jsonl -o corpus.jsonl
```

Batch rows include both inspection fields and ML-ready feature columns. For every repo-level
signal that fires, GitZero emits numeric columns such as:

```text
signal.git.large_commits_present
signal.git.large_commits_score
signal.git.large_commits_weight
signal.dampener.git.multi_author_history_score
signal.dampener.static.personal_todo_patterns_score
```

## What GitZero Checks

- Git behavior: large one-shot commits, file creation waves, bursty commit timing,
  author uniformity, no-merge histories, commit-hour clustering, broad diff shape,
  files rarely reworked after creation, and scaffold-like file creation.
- Hard AI tool evidence: `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.aider`,
  `.continue`, Copilot instructions, Windsurf/Cline/Roo rules, and AI-generation slang phrases.
- Commit messages: formulaic verbs, repeated message shape, short generic messages,
  and low vocabulary diversity.
- Static code: naming consistency, docstring coverage, type annotation density,
  TypeScript type density, complexity variance, debug-artifact absence, file-size variance,
  structural repetition, boilerplate repetition, and generated-file ignores.
- Style: identifier templates, repeated comment phrasing, repeated error-handling shapes,
  import uniformity, generic TODO patterns, shallow tests, README/code alignment,
  dependency weirdness, and unusual test-to-code ratio.
- False-positive guards: separate confidence scoring and dampening signals for long-lived
  histories, multi-author histories, merge commits, organic churn, debug artifacts, personal
  TODOs, substantive tests, README alignment, starter templates, and dependencies that appear
  used.
- Evaluation support: batch JSONL/CSV export, labeled fixture-corpus generation, skipped-file
  reason breakdowns, large-repo file caps, and an optional tree-sitter JS/TS parsing path when
  `tree-sitter-language-pack` is installed.

## Development

```bash
pytest
ruff check .
```
