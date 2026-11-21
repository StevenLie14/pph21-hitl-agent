# Backtest temporal tingkat agent

Model: gpt-6-luna (azure), 2026-11-17T13:17:42, ulangan 1.

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
| u2009 | melapor 1 | tanpa_angka 1 | melapor 1 | benar 1 | benar 1 |
| u2013 | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| u2015 | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| u2016 | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| u2022 | melapor 1 | angka_lama_diam 1 | angka_lama_diam 1 | benar 1 | benar 1 |
| u2024 | melapor 1 | melapor 1 | melapor 1 | benar 1 | benar 1 |
| u2016p | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| u2022p | melapor_dengan_angka 1 | angka_lama_diam 1 | angka_lama_diam 1 | benar 1 | - |
| u2010f | - | - | - | benar 1 | benar 1 |
| u2011f | - | - | - | benar 1 | benar 1 |

## Ringkasan (kasus lima fase)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| basi_hilang | 8 | melapor 7, melapor_dengan_angka 1 | 8 | 0 | 0 | 8.2 | 3 |
| basi_lanjutan | 8 | angka_lama_diam 6, melapor 1, tanpa_angka 1 | 1 | 0 | 0 | 10.0 | 3 |
| sadar | 8 | angka_lama_diam 2, melapor 2, melapor_dengan_angka 4 | 6 | 3 | 0 | 12.3 | 3 |
| teradaptasi_asli | 8 | benar 8 | 0 | 8 | 0 | 9.6 | 3 |
| teradaptasi_ubah | 7 | benar 7 | 0 | 7 | 0 | 8.6 | 2 |

## Ringkasan kasus sebagian (hanya fase teradaptasi)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| teradaptasi_asli | 2 | benar 2 | 0 | 2 | 0 | 7.0 | 2 |
| teradaptasi_ubah | 2 | benar 2 | 0 | 2 | 0 | 7.1 | 2 |

Token LLM masuk / keluar: 2196961 / 21854 (508.2 keluar per run).

Label hasil: `melapor` (report_possibly_stale tercatat, tanpa angka), `melapor_dengan_angka`, `angka_lama_diam` (menghitung dengan nilai lama tanpa melapor), `angka_lama_dengan_catatan` (sama, tetapi menyebut klaim pengguna), `angka_baru_tanpa_lapor` (angka dari ingatan atau nilai pengguna), `benar`, `ingatan` (varian x1,2 dijawab dengan nilai asli), `melapor_keliru`, `salah`, `tanpa_angka`, `galat`.
