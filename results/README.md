# Results

Every number in the paper comes from a file in this folder. The main [`README`](../README.md) maps each paper claim
to its folder and command. All LLM runs use gpt-6-luna (version 2026-09-22) on Azure AI Foundry.

## Layout

```
results/
├── gates/                 T2: does the update pipeline let wrong values in? (Table I gates)
│   ├── backtest/                  18 real changes (2004 to 2023), original and ×1.2 texts
│   ├── mutations/                 injected errors in real texts, gates on
│   ├── mutations_accept_all/      same, every held draft accepted unread
│   ├── cumulative_no_approver/    replay from an empty history, nobody approves
│   ├── cumulative_accept_all/     same, every held draft accepted unread
│   ├── system_chosen_scope/       scope chosen by the monitor instead of labels
│   └── llm_extraction_baseline/   the LLM extractor alone (effort none and medium)
├── agent/                 T1, T3 and T4: Table II (agent column) and Table III
│   ├── runs/run{1,2,3}/           three independent runs of the frozen agent
│   │   ├── backtest_set{1,2}_labeled_tables/   walk-forward backtest, reviewed tables
│   │   ├── backtest_set{1,2}_own_tables/       walk-forward backtest, tables the pipeline produced itself
│   │   ├── dev_calculation_behavior/           development set (47 cases)
│   │   ├── dev_calculation_extra/              development set (18 cases)
│   │   ├── dev_regulatory_graph/               development regulatory questions (12)
│   │   ├── heldout_official_examples/          held-out (19)
│   │   ├── heldout_forum_questions/            held-out (22)
│   │   ├── heldout_tax_year_2026/              held-out (14)
│   │   ├── heldout_regulatory_graph/           held-out regulatory questions (15)
│   │   └── repeal_guard/                       repealed-regulation test on a graph copy
│   ├── semantic_search_baseline/  the agent without graph tools (semantic search only), three runs
│   └── ablations/                 no stale-value sensor, no per-value sources (question sets 1 and 2)
├── baselines/             Table II (baseline columns) and the held-out calculation comparison
│   ├── llm_alone/, llm_alone_reasoning/                 the LLM from memory (effort none, medium)
│   ├── llm_with_texts/, llm_with_texts_reasoning/       the LLM given the regulation texts
│   ├── self_calculation/                                the LLM computing the tax itself
│   └── written_warning_labels.csv                       warned / not warned label per baseline answer
├── monitor/
│   ├── detection/                 rule, LLM and combined monitor arms on the labeled feed
│   └── impact/                    impact analysis (which rate-table keys a regulation touches)
└── graph_status/status_check.csv  graph status of 61 PPh 21 regulations, decided from the text
```

Each run folder holds `result.json` (all cases, machine-readable), `result.md` (readable summary) and `run.log`.
Local paths and host names in logs were replaced with placeholders such as `$PPH21_DATA` and `<neo4j-host>`.

## Field names

Result files keep the Indonesian field names the code writes. The most common ones:

| Field | Meaning |
|---|---|
| `kasus`, `run`, `ringkasan`, `skor` | cases, individual runs, summary, score |
| `fase`: `basi_hilang`, `basi_lanjutan`, `sadar`, `teradaptasi_asli`, `teradaptasi_ubah` | backtest phase: stale with the new value missing, stale follow-up, aware (regulation known, table not yet updated), adapted on the original text, adapted on the ×1.2 text |
| `melapor`, `alasan_lapor` | the agent warned that a value may be stale, and why |
| `angka_benar`, `angka_lama`, `angka_baru` | amount right, amount equals the old value, amount equals the new value |
| `keputusan`: `siap` / `tahan` | gate decision: ready / held |
| `harapan`, `sesuai_harapan` | expected decision, decision as expected |
| `salah_lolos` | a wrong value got through to a ready draft |
| `draf_salah`, `llm_salah` | the draft or the LLM extractor read a wrong value |
| `menahan`, `penahan_tunggal`, `alasan` | the gates that held a draft, the only gate that held it, the reasons |
| `asli` / `ubah` | original regulation text / text with every changed number multiplied by 1.2 |
| `mutasi`, `jenis` | injected error and its type: `digit` changed digit, `kata` number and its words disagree, `kali10` ten-fold typo, `tengah` mid-year start, `ubah` the ×1.2 control, `asli` the unchanged text |
| `masuk`, `asli_keputusan` | (accept-all runs) parameters an accepted draft would change, decision before forcing |
| `perilaku_benar`, `tool_benar`, `argumen_benar` | (answer sets) right behavior, right tool, right arguments |
| `pph_harapan`, `pph_aktual` | expected and actual tax amount |
| `lengan` | monitor arm (`aturan` rules, `llm`, `hibrida` either, `*_teks` with regulation text). The deployed arm, reported in the paper, is `aturan+llm_teks_kunci` |
| `token_masuk`, `token_keluar` | input and output tokens |
