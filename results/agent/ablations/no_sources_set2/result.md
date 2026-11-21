# Backtest temporal tingkat agent

Model: gpt-6-luna (azure), 2026-11-17T21:35:56, ulangan 3.

Tabel: label.

Dunia beku: tabel tarif, regulasi.yaml (tanpa ringkasan), provenans (kosong), graf (peraturan yang terbit pada/sesudah tanggal potong disembunyikan; FAQ mati). Tidak beku: kode, prompt, dan dasar_hukum bawaan mesin.

## Kasus

| Kasus | Peristiwa | Beku | Jeda ke 1 Jan (hari) | Patch | Kunci ditinjau | PPh lama | PPh baru | PPh x1,2 |
|---|---|---|---|---|---|---|---|---|
| u2009 | UU 36 Tahun 2008, PMK 250 Tahun 2008, PMK 254 Tahun 2008 | 2008-09-23 | 100 | manusia | 19 | - | 13324000 | 12246720 |
| u2013 | PMK 162 Tahun 2012, PMK 206 Tahun 2012 | 2012-10-22 | 71 | manusia | 5 | 13324000 | 12055000 | 11326000 |
| u2015 | PMK 122 Tahun 2015 | 2015-06-29 | -179 | pipeline | 4 | 12055000 | 10300000 | 9220000 |
| u2016 | PMK 101 Tahun 2016 | 2016-06-22 | -173 | pipeline | 4 | 10300000 | 7600000 | 5980000 |
| u2022 | UU 7 Tahun 2021 | 2021-10-29 | 64 | manusia | 14 | 7600000 | 6600000 | 5400000 |
| u2024 | PP 58 Tahun 2023, PMK 168 Tahun 2023 | 2023-12-27 | 5 | manusia | 263 | - | 480000 | 360000 |
| u2016p | PMK 101 Tahun 2016 | 2016-06-22 | -173 | pipeline | 4 | 2430000 | 1305000 | 630000 |
| u2022p | UU 7 Tahun 2021 | 2021-10-29 | 64 | manusia | 14 | 2740000 | 2580000 | 2580000 |
| u2010f | PP 68 Tahun 2009 | 2009-11-16 | 46 | manusia | 12 | - | 17500000 | 17000000 |
| u2011f | PP 80 Tahun 2010 | 2010-12-20 | 12 | manusia | 4 | - | 1200000 | 1280000 |

## Hasil per fase

| Kasus | basi_hilang | basi_lanjutan | sadar | teradaptasi_asli | teradaptasi_ubah |
|---|---|---|---|---|---|
| u2009 | - | tanpa_angka 3 | melapor 3 | benar 3 | benar 3 |
| u2013 | - | angka_lama_diam 3 | melapor_dengan_angka 3 | benar 3 | benar 2, tanpa_angka 1 |
| u2015 | - | angka_lama_diam 3 | melapor_dengan_angka 3 | benar 3 | benar 3 |
| u2016 | - | angka_lama_diam 3 | melapor_dengan_angka 3 | benar 3 | benar 3 |
| u2022 | - | angka_lama_diam 3 | angka_lama_diam 3 | benar 3 | benar 3 |
| u2024 | - | tanpa_angka 3 | melapor 3 | benar 3 | benar 2, tanpa_angka 1 |
| u2016p | - | angka_lama_diam 3 | melapor_dengan_angka 3 | benar 3 | benar 3 |
| u2022p | - | angka_lama_diam 3 | angka_lama_diam 3 | benar 3 | - |
| u2010f | - | - | - | benar 3 | benar 3 |
| u2011f | - | - | - | benar 3 | benar 3 |

## Ringkasan (kasus lima fase)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| basi_lanjutan | 24 | angka_lama_diam 18, tanpa_angka 6 | 0 | 0 | 18 | 12.6 | 3 |
| sadar | 24 | angka_lama_diam 6, melapor 6, melapor_dengan_angka 12 | 18 | 16 | 18 | 13.0 | 3 |
| teradaptasi_asli | 24 | benar 24 | 0 | 3 | 21 | 11.1 | 3 |
| teradaptasi_ubah | 21 | benar 19, tanpa_angka 2 | 0 | 2 | 17 | 11.2 | 3 |

## Ringkasan kasus sebagian (hanya fase teradaptasi)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| teradaptasi_asli | 6 | benar 6 | 0 | 6 | 0 | 7.7 | 2 |
| teradaptasi_ubah | 6 | benar 6 | 0 | 6 | 0 | 8.7 | 2 |

Token LLM masuk / keluar: 5099850 / 62120 (591.6 keluar per run).

Label hasil: `melapor` (report_possibly_stale tercatat, tanpa angka), `melapor_dengan_angka`, `angka_lama_diam` (menghitung dengan nilai lama tanpa melapor), `angka_lama_dengan_catatan` (sama, tetapi menyebut klaim pengguna), `angka_baru_tanpa_lapor` (angka dari ingatan atau nilai pengguna), `benar`, `ingatan` (varian x1,2 dijawab dengan nilai asli), `melapor_keliru`, `salah`, `tanpa_angka`, `galat`.
