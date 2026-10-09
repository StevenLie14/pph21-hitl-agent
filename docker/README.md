# Docker images for the corpus pipeline

One `Dockerfile`, three images:

| Image | Contents | Host needs |
|---|---|---|
| `pph21-korpus` | Scrape JDIH and pajak.go.id, quality check, merge, relation extraction, legal basis, write the `neo4j-v2` graph | Docker only |
| `pph21-ocr` | PaddleOCR PP-OCRv6 for scanned PDFs | NVIDIA GPU, driver, NVIDIA Container Toolkit |
| `pph21-embed` | Gemini vectors (`gemini-embedding-2`, through the API) for text chunks and FAQ | Docker only, `GOOGLE_API_KEY` |

They are separate because the CUDA stack (about 6 GB) is not needed by the CPU stages, and OCR stays on Python 3.11
so that its text is identical to the published corpus (checked with calibration documents).

## Usage

From the repository root:

```bash
cp docker/neo4j.env.example docker/neo4j.env      # fill in NEO4J_V2_URI / USER / PASSWORD
docker compose -f docker/compose.yaml build korpus

# corpus data on the host; point at an existing folder to avoid scraping again
export PPH21_DATA_HOST=/path/to/pajak_data

docker compose -f docker/compose.yaml run --rm korpus           # the whole chain
docker compose -f docker/compose.yaml run --rm korpus mutu      # resume from the "mutu" (quality) stage
docker compose -f docker/compose.yaml --profile gpu up -d ocr   # OCR, runs until downloads are finished
```

Stages, in order: `jdih_daftar`, `jdih_halaman`, `jdih_unduh` (JDIH list, pages, downloads), `pajak_daftar`,
`pajak_detail` (pajak.go.id list and details), `mutu` (quality), `gabung` (merge), `relasi_klaim`, `relasi_bukti`,
`relasi_teks` (relation claims, evidence, text), `dasar_hukum` (legal basis), `graf_tulis` (write graph), `faq_graf`
(DJP FAQ into the graph). Logs are in `<data>/log_perbarui_korpus.txt` and `<data>/korpus_jdih/log_ocr.txt`.

`graf_tulis` clears and reloads the graph at `NEO4J_V2_URI`, including vectors, so the vectors are written again
after the chain:

```bash
GOOGLE_API_KEY=... docker compose -f docker/compose.yaml --profile vektor run --rm embed
```

The agent uses Gemini vectors truncated to 768 dimensions (property `embedding_gemini`, indexes
`chunk_vector_gemini` and `faq_vector_gemini`). The embedding cache is keyed by the SHA-1 of the text, so only
changed chunks cost API calls.

To try it without touching a remote graph, run a local Neo4j (`--profile lokal`, set `NEO4J_AUTH=neo4j/<password>`
and `NEO4J_V2_URI=bolt://neo4j:7687` in `docker/neo4j.env`).

## Notes

- Inside the container the data location is `PPH21_DATA=/data` (`taxagent/paths.py`).
- The PP-OCRv6 model is downloaded once into the `ocr-model` volume on the first OCR run.
- Containers run as user `pph21` (uid 1000), not root. The host data folder must be writable by that uid.
- No LLM key is needed for these stages and none is put into the containers.
