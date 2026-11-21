# Backtest temporal tingkat agent

Model: gpt-6-luna (azure), 2026-11-17T13:32:09, ulangan 1.

Tabel: sendiri (umpan ke jawaban) (hasil_evaluasi/akhir_20261117/kumulatif/draf_kumulatif_umpan_ke_jawaban.json).

Dunia beku: tabel tarif, regulasi.yaml (tanpa ringkasan), provenans (kosong), graf (peraturan yang terbit pada/sesudah tanggal potong disembunyikan; FAQ mati). Tidak beku: kode, prompt, dan dasar_hukum bawaan mesin.

## Kasus

| Kasus | Peristiwa | Beku | Jeda ke 1 Jan (hari) | Patch | Kunci ditinjau | PPh lama | PPh baru | PPh x1,2 |
|---|---|---|---|---|---|---|---|---|
| u2009 | UU 36 Tahun 2008, PMK 250 Tahun 2008, PMK 254 Tahun 2008 | 2008-09-23 | 100 | sistem | 19 | - | - | - |
| u2013 | PMK 162 Tahun 2012, PMK 206 Tahun 2012 | 2012-10-22 | 71 | sistem | 5 | - | - | - |
| u2015 | PMK 122 Tahun 2015 | 2015-06-29 | -179 | sistem | 4 | - | - | - |
| u2016 | PMK 101 Tahun 2016 | 2016-06-22 | -173 | sistem | 4 | - | - | - |
| u2022 | UU 7 Tahun 2021 | 2021-10-29 | 64 | sistem | 14 | - | - | - |
| u2024 | PP 58 Tahun 2023, PMK 168 Tahun 2023 | 2023-12-27 | 5 | sistem | 263 | - | - | - |
| u2016p | PMK 101 Tahun 2016 | 2016-06-22 | -173 | sistem | 4 | - | - | - |
| u2022p | UU 7 Tahun 2021 | 2021-10-29 | 64 | sistem | 14 | - | - | - |
| u2010f | PP 68 Tahun 2009 | 2009-11-16 | 46 | sistem | 12 | - | - | - |
| u2011f | PP 80 Tahun 2010 | 2010-12-20 | 12 | sistem | 4 | - | - | - |

## Hasil per fase

| Kasus | basi_hilang | basi_lanjutan | sadar | teradaptasi_asli | teradaptasi_ubah |
|---|---|---|---|---|---|
| u2009 | melapor 1 | tanpa_angka 1 | melapor 1 | tanpa_angka 1 | - |
| u2013 | melapor 1 | tanpa_angka 1 | melapor 1 | tanpa_angka 1 | - |
| u2015 | melapor 1 | tanpa_angka 1 | melapor 1 | tanpa_angka 1 | - |
| u2016 | melapor 1 | tanpa_angka 1 | melapor 1 | tanpa_angka 1 | - |
| u2022 | melapor 1 | tanpa_angka 1 | tanpa_angka 1 | tanpa_angka 1 | - |
| u2024 | melapor 1 | tanpa_angka 1 | melapor 1 | tanpa_angka 1 | - |
| u2016p | melapor 1 | tanpa_angka 1 | melapor 1 | tanpa_angka 1 | - |
| u2022p | melapor 1 | tanpa_angka 1 | tanpa_angka 1 | tanpa_angka 1 | - |
| u2010f | - | - | - | tanpa_angka 1 | - |
| u2011f | - | - | - | tanpa_angka 1 | - |

## Ringkasan (kasus lima fase)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| basi_hilang | 8 | melapor 8 | 8 | 0 | 0 | 8.8 | 3 |
| basi_lanjutan | 8 | tanpa_angka 8 | 0 | 0 | 0 | 12.0 | 5 |
| sadar | 8 | melapor 6, tanpa_angka 2 | 6 | 4 | 0 | 14.1 | 4 |
| teradaptasi_asli | 8 | tanpa_angka 8 | 0 | 0 | 0 | 11.4 | 4 |

## Ringkasan kasus sebagian (hanya fase teradaptasi)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| teradaptasi_asli | 2 | tanpa_angka 2 | 0 | 0 | 0 | 9.4 | 4 |

Token LLM masuk / keluar: 2395314 / 13456 (395.8 keluar per run).

Label hasil: `melapor` (report_possibly_stale tercatat, tanpa angka), `melapor_dengan_angka`, `angka_lama_diam` (menghitung dengan nilai lama tanpa melapor), `angka_lama_dengan_catatan` (sama, tetapi menyebut klaim pengguna), `angka_baru_tanpa_lapor` (angka dari ingatan atau nilai pengguna), `benar`, `ingatan` (varian x1,2 dijawab dengan nilai asli), `melapor_keliru`, `salah`, `tanpa_angka`, `galat`.
