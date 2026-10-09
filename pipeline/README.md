# Corpus and graph pipeline

Builds the regulatory graph (`neo4j-v2`) from JDIH Kemenkeu and pajak.go.id. Run from the repository root, in this
order. Data goes to `$PPH21_DATA`. Environments: `thesis` unless noted, `ocr_gpu` has PaddleOCR, `embed` computes the
Gemini vectors. `docker/update_corpus.sh` chains steps 1, 2, 4, 5, 7, 8, 9, 12, 13 and the `faq.py graph` part of 14.
Steps 6, 10 and 11 are run by hand; `build_graph.py` reads their outputs when they exist.

| # | Command | Output |
|---|---|---|
| 1 | `python pipeline/corpus_jdih.py list`, then `pages`, then `download` | JDIH listing, detail pages, PDFs |
| 2 | `python pipeline/corpus_pajak.py list`, then `detail` | pajak.go.id listing and detail pages |
| 3 | `conda run -n ocr_gpu python pipeline/ocr_corpus.py --follow` | OCR text of scanned PDFs (`paddle_common.py` holds the settings) |
| 4 | `python pipeline/corpus_quality.py assess` | text quality per document |
| 5 | `python pipeline/merge_corpus.py` | one index over both sources |
| 6 | `python pipeline/split_words_corpus.py lexicon` | lexicon for splitting joined words |
| 7 | `python pipeline/relation_claims.py` | repeal and amend claims from JDIH |
| 8 | `python pipeline/relation_evidence.py` | claims checked against the regulation text |
| 9 | `python pipeline/relation_text.py` | relations found in the closing articles |
| 10 | `python pipeline/relation_remaining_llm.py` | sentences the patterns could not read, read by the LLM and checked by code |
| 11 | `python pipeline/relation_claims_llm.py --arm search --adopt` | JDIH claims without text evidence, checked by the LLM |
| 12 | `python pipeline/legal_basis.py` | legal basis (Mengingat) edges |
| 13 | `python pipeline/build_graph.py --write` | the graph in `neo4j-v2` |
| 14 | `python pipeline/faq.py collect`, `conda run -n ocr_gpu python pipeline/ocr_faq.py`, `python pipeline/faq.py graph` | DJP FAQ nodes |
| 15 | `conda run -n embed python pipeline/embed.py gemini compute --faq`, then `gemini write` | vectors for text search |

`ocr_file.py` and `ocr_boxes.py` are not pipeline steps: the monitor (`taxagent/monitor/ocr.py`) and the TER table
extractor (`taxagent/update/ter_table.py`) call them for new regulations.
