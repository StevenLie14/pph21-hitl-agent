# A Human-in-the-Loop Adaptive Large Language Model Agent for Indonesian Employee Income Tax

Code, test data and results for the paper of the same name (BTS-I2C 2026, submitted). The paper is [`paper.pdf`](paper.pdf).
The history is condensed from the private development repository: each commit is dated when that part was first built and holds its final version.

The system answers PPh 21 questions with an LLM agent, but every tax amount comes from a deterministic engine that
reads a versioned rate table. When a new regulation appears, a monitor flags it, two independent extractors (pattern
rules and an LLM) propose new rate-table values, eight deterministic gates (G1 to G8) decide whether a draft is
ready or held, and a human approves the patch. The paper asks whether an LLM can help keep that table current
without letting wrong values in.

## What is in this repository

| Path | Contents |
|---|---|
| `taxagent/taxes/pph21/calc/` | Deterministic PPh 21 engine (annual Pasal 17, monthly TER, final rates). |
| `taxagent/taxes/pph21/data/` | Rate tables `tarif_2024..2026.yaml`, the skill manifest, and all evaluation sets (see below). |
| `taxagent/agent/`, `taxagent/tools/` | The agent loop, its tools, the PTKP status guard and the citation checker. |
| `taxagent/monitor/` | Regulation monitor (JDIH Kemenkeu feed and pajak.go.id listing), rule and LLM classifiers, impact analysis. |
| `taxagent/update/` | Draft extraction (pattern and LLM, LLM vision for attachment tables), gates G1 to G8, review, patch, backtest and fault injection tests. |
| `taxagent/corpus/` | Corpus, relation and graph code (Neo4j regulatory graph with text-evidenced repeal and amend edges). |
| `taxagent/evaluation/` | Scorers for the agent evaluation and the agent backtest. |
| `pipeline/` | One pipeline that builds the regulatory graph from public sources (order in `pipeline/README.md`). `ocr_file.py` and `ocr_boxes.py` are also called by the monitor and the TER table extractor. |
| `experiments/` | Evaluation-only scripts for results the CLI does not produce (baselines, accept-all runs, repeal guard). |
| `docker/` | Images used to build the corpus and re-run OCR. |
| `tests/` | Unit tests (no API key, no graph, no corpus needed). |
| `results/` | Every result reported in the paper (see the claim map below). |
| `paper.pdf` | The paper as submitted. |

Not included: the regulation corpus (14,109 regulations with PDFs, OCR pages and vectors), the Neo4j
graph dump, the LLM response caches, and the web application used in deployment. The corpus can be rebuilt from
public sources with the scripts in `pipeline/`, in the order given in `pipeline/README.md`.

Most identifiers, data fields and result files keep Indonesian names (for example `tahan` = held, `siap` = ready,
`basi` = stale, `sadar` = aware, `teradaptasi` = adapted). Legal terms stay Indonesian.

## Setup

Python 3.10 or later.

```bash
pip install -e ".[agent,graph,monitor,dev]"
cp .env.example .env        # then fill in the keys you need
pytest -q                   # 1,346 tests (41 more skip), no key or network needed
ruff check taxagent tests pipeline experiments
```

The engine works without any key:

```bash
python -m taxagent.cli calculate --help
python -m taxagent.cli rates --year 2026
```

Runs that call the LLM need an Azure AI Foundry deployment (the paper uses gpt-6-luna, version 2026-09-22). Runs
that use the agent's graph tools also need the Neo4j graph (`NEO4J_V2_*`). The draft tests need the pajak.go.id
text dataset (`pajak_details.json`, built by `pipeline/corpus_pajak.py`) and the attachment PDFs under
`PPH21_DATA`.

## Code version used for the results

The code here is the frozen evaluation code: tag `beku-run-akhir-2026-11-17e` (the agent runs) plus evaluation-only
ablation switches (`PPH21_ABLATION_SENSOR`, `PPH21_ABLATION_SOURCES`, `PPH21_GRAF_ABLASI`). The draft tests ran
one commit earlier with identical draft and gate code. The two "accept all" runs (2026-11-20) patch the decision
in-process only, see `experiments/accept_all_*.py`. The web front end and deployment files were removed
from this copy because the paper does not use them, as was a relation-extraction evaluation. Code comments and
docstrings were also removed, the program logic is unchanged.

## Evaluation sets

All in `taxagent/taxes/pph21/data/`.

| File | Used for |
|---|---|
| `kasus_agent.yaml` | Calculation and behavior (development set). |
| `kasus_agent_holdout.yaml` | More development calculation cases (counted with the set above in Table III). |
| `kasus_agent_graf.yaml`, `kasus_agent_uji_graf.yaml` | Regulatory questions that need the graph (development and held-out). |
| `kasus_agent_uji_resmi.yaml` | Worked examples from the official regulation (PMK 168/2023). |
| `kasus_agent_uji_alami.yaml` | Questions from a public tax forum. Only paraphrases and URLs are stored, the original wording is not redistributed. |
| `kasus_agent_uji_2026.yaml` | Tax year 2026 questions. |
| `kasus_backtest_agent.yaml`, `kasus_backtest_agent_uji.yaml` | Agent walk-forward backtest, question sets 1 and 2 (Table II). |
| `peristiwa_backtest.yaml` | The 18 real rate-table changes from 2004 to 2023 replayed by the draft tests, with expected decisions. |
| `pantau_evaluasi.yaml`, `dampak_label.yaml`, `draf_label.yaml` | Labeled sets for the monitor, impact analysis and drafts. |
| `riwayat_tarif_per_tahun.yaml` | Answer key of the cumulative replay: the true values per tax year and what changed from the year before (built from `draf_label.yaml` and `peristiwa_backtest.yaml`). |

## Claim map: paper → results → command

All result folders are under `results/`. Each run folder holds `result.json` (every case, machine-readable),
`result.md` (readable summary) and `run.log`. [`results/README.md`](results/README.md) explains the layout. Absolute local paths and host names in logs were replaced with placeholders.

The paper orders its tests by adaptation stage: T1 before adaptation, T2 during, T3 after, T4 no regulation change.

### T2 during adaptation: does the update pipeline let wrong values in?

| Paper claim | Folder | Command |
|---|---|---|
| Replay of 18 real changes, 4 of the 11 changes no gate should hold became ready, the same on the synthetic texts (values ×1.2) | `gates/backtest/` | `python -m taxagent.cli draft-backtest --text-dataset <pajak_details.json> --llm --lampiran-tables` |
| Gates hold every injected error (fault injection) | `gates/mutations/` | `python -m taxagent.cli draft-evaluate --text-dataset <...> --llm --lampiran-tables --parallel 1` |
| Accepting every held draft would let in 172 of 464 injected errors (74 ten-fold, 80 mid-year) | `gates/mutations_accept_all/` | `python experiments/accept_all_mutations.py --text-dataset <...> --output <dir>` |
| Cumulative replay from zero with no approver | `gates/cumulative_no_approver/` | `draft-backtest ... --cumulative --phase1-llm` |
| Same, every held draft accepted unread | `gates/cumulative_accept_all/` | `python experiments/accept_all_backtest.py --text-dataset <...> --output <dir>` |
| Scope chosen by the system instead of labels | `gates/system_chosen_scope/` | `draft-backtest ... --phase1-llm` |
| LLM extractor alone with reasoning (baseline) | `gates/llm_extraction_baseline/` | `python experiments/extraction_reasoning.py` |

### T3 after adaptation: does the agent answer correctly after an update? (Table II)

| Paper claim | Folder | Command |
|---|---|---|
| Stale, aware and adapted phases, amounts right in all 48 adapted and all 45 synthetic runs (values ×1.2) | `agent/runs/run{1,2,3}/backtest_set{1,2}_labeled_tables/` | `python -m taxagent.cli agent-backtest --cases <set> --repeat 1 --draft-backtest results/gates/backtest/result.json` |
| Same with the tables the pipeline produced itself (feed to answer) | `agent/runs/run{1,2,3}/backtest_set{1,2}_own_tables/` | same, plus `--own-tables results/gates/cumulative_no_approver/result.json` |

### T1 before adaptation: is it safe between a new regulation and its approved update?

| Paper claim | Folder | Command |
|---|---|---|
| Never used unreviewed values (0 of 48), warned in 42 of 48 | `agent/runs/*/backtest_set*_labeled_tables/` (aware phase) | as above |
| Repeal guard: warned in all 12 runs after the repeal, silent before and on the real graph | `agent/runs/run{1,2,3}/repeal_guard/` | `python experiments/repeal_guard_eval.py --runs 1 --output <file>` |
| Monitor: 115 flagged, 40 of 41 changes found, 75 false alarms (precision 35%) | `monitor/detection/` | `python -m taxagent.cli monitor-evaluate-llm --repeats 3 --text-repeats 3 --text-dataset <...>` |
| Impact analysis key recall | `monitor/impact/` | `python -m taxagent.cli monitor-impact --text-dataset <...>` |
| Graph status right for 58 of the 61 PPh 21 regulations | `graph_status/status_check.csv` | manual check, see below |

### T4 no regulation change: answering today (Table III), and the baselines (Table II)

| Paper row | Folder | Command |
|---|---|---|
| Calculation and behavior (65 = 47 + 18) | `agent/runs/run*/dev_calculation_behavior/`, `agent/runs/run*/dev_calculation_extra/` | `python -m taxagent.cli evaluate --dataset taxagent/taxes/pph21/data/kasus_agent.yaml`, then `kasus_agent_holdout.yaml` |
| Regulatory graph (dev) | `agent/runs/run*/dev_regulatory_graph/` | `evaluate --dataset .../kasus_agent_graf.yaml` |
| Official examples | `agent/runs/run*/heldout_official_examples/` | `evaluate --dataset .../kasus_agent_uji_resmi.yaml` |
| Forum questions | `agent/runs/run*/heldout_forum_questions/` | `evaluate --dataset .../kasus_agent_uji_alami.yaml --original-questions <file>` |
| Tax year 2026 | `agent/runs/run*/heldout_tax_year_2026/` | `evaluate --dataset .../kasus_agent_uji_2026.yaml` |
| Regulatory, graph (held-out) | `agent/runs/run*/heldout_regulatory_graph/` | `evaluate --dataset .../kasus_agent_uji_graf.yaml` |
| Regulatory, semantic search | `agent/semantic_search_baseline/run{1,2,3}/` | same as held-out graph, with `PPH21_GRAF_ABLASI=1` |
| Ablations: without the stale-value sensor or the source rule | `agent/ablations/no_sensor_set*`, `agent/ablations/no_sources_set*` | `agent-backtest` with `PPH21_ABLATION_SENSOR=0` or `PPH21_ABLATION_SOURCES=0` |
| LLM alone, effort none and medium | `baselines/llm_alone/`, `baselines/llm_alone_reasoning/` | `python experiments/llm_only_backtest.py` |
| LLM with the regulation texts, effort none and medium | `baselines/llm_with_texts/`, `baselines/llm_with_texts_reasoning/` | `python experiments/rag_backtest.py` |
| LLM computing the tax itself, at most 85% right (133 of 156) | `baselines/self_calculation/{no_reasoning,reasoning_medium}.*` | `python experiments/llm_self_calculation.py --runs 3 --tag <tag>` |
| Same, on the 28 held-out calculations, at most 64 of 84 right | `baselines/self_calculation/heldout_*` | `python experiments/llm_self_calculation.py --cases heldout --runs 3 --tag <tag>` |
| Written warnings in baseline answers (LLM with texts, labeled by hand; the LLM-alone answers match no warning phrase in any phase, so they were not labeled) | `baselines/written_warning_labels.csv` | `python experiments/baseline_warnings.py results/baselines/llm_alone results/baselines/llm_with_texts ...` |

Confidence intervals (Wilson) and the McNemar test are computed by the scorers in `taxagent/evaluation/`
and `taxagent/monitor/` and appear in the `.md` summaries.

### Graph status check

The 61 PPh 21 regulations from the monitor and backtest sets were checked against a commercial tax database, and
every disagreement was decided from the regulation text. The database's labels and pages are not redistributed.
`results/graph_status/status_check.csv` keeps, per regulation, the graph status, the regulations the graph says
changed it, the status decided from the text and whether the graph was right.
