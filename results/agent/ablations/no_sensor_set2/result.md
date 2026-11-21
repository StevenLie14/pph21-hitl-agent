# Backtest temporal tingkat agent

Model: gpt-6-luna (azure), 2026-11-17T20:50:37, ulangan 3.

Tabel: label.

Dunia beku: tabel tarif, regulasi.yaml (tanpa ringkasan), provenans (kosong), graf (peraturan yang terbit pada/sesudah tanggal potong disembunyikan; FAQ mati). Tidak beku: kode, prompt, dan dasar_hukum bawaan mesin.

## Kasus

| Kasus | Peristiwa | Beku | Jeda ke 1 Jan (hari) | Patch | Kunci ditinjau | PPh lama | PPh baru | PPh x1,2 |
|---|---|---|---|---|---|---|---|---|
| u2009 | UU 36 Tahun 2008, PMK 250 Tahun 2008, PMK 254 Tahun 2008 | 2008-09-23 | 100 | manusia | 19 | - | 13324000 | - |
| u2013 | PMK 162 Tahun 2012, PMK 206 Tahun 2012 | 2012-10-22 | 71 | manusia | 5 | 13324000 | 12055000 | - |
| u2015 | PMK 122 Tahun 2015 | 2015-06-29 | -179 | pipeline | 4 | 12055000 | 10300000 | - |
| u2016 | PMK 101 Tahun 2016 | 2016-06-22 | -173 | pipeline | 4 | 10300000 | 7600000 | - |
| u2022 | UU 7 Tahun 2021 | 2021-10-29 | 64 | manusia | 14 | 7600000 | 6600000 | - |
| u2024 | PP 58 Tahun 2023, PMK 168 Tahun 2023 | 2023-12-27 | 5 | manusia | 263 | - | 480000 | - |
| u2016p | PMK 101 Tahun 2016 | 2016-06-22 | -173 | pipeline | 4 | 2430000 | 1305000 | - |
| u2022p | UU 7 Tahun 2021 | 2021-10-29 | 64 | manusia | 14 | 2740000 | 2580000 | - |
| u2010f | PP 68 Tahun 2009 | 2009-11-16 | 46 | manusia | 12 | - | 17500000 | - |
| u2011f | PP 80 Tahun 2010 | 2010-12-20 | 12 | manusia | 4 | - | 1200000 | - |

## Hasil per fase

| Kasus | basi_hilang | basi_lanjutan | sadar | teradaptasi_asli | teradaptasi_ubah |
|---|---|---|---|---|---|
| u2009 | - | - | tanpa_angka 3 | - | - |
| u2013 | - | - | angka_lama_diam 1, melapor_dengan_angka 2 | - | - |
| u2015 | - | - | melapor_dengan_angka 3 | - | - |
| u2016 | - | - | angka_lama_dengan_catatan 1, melapor_dengan_angka 2 | - | - |
| u2022 | - | - | angka_lama_diam 3 | - | - |
| u2024 | - | - | tanpa_angka 3 | - | - |
| u2016p | - | - | angka_lama_diam 2, melapor_dengan_angka 1 | - | - |
| u2022p | - | - | angka_lama_diam 3 | - | - |
| u2010f | - | - | - | - | - |
| u2011f | - | - | - | - | - |

## Ringkasan (kasus lima fase)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| sadar | 24 | angka_lama_dengan_catatan 1, angka_lama_diam 9, melapor_dengan_angka 8, tanpa_angka 6 | 8 | 4 | 0 | 16.0 | 4 |

Token LLM masuk / keluar: 1846689 / 18504 (771.0 keluar per run).

Label hasil: `melapor` (report_possibly_stale tercatat, tanpa angka), `melapor_dengan_angka`, `angka_lama_diam` (menghitung dengan nilai lama tanpa melapor), `angka_lama_dengan_catatan` (sama, tetapi menyebut klaim pengguna), `angka_baru_tanpa_lapor` (angka dari ingatan atau nilai pengguna), `benar`, `ingatan` (varian x1,2 dijawab dengan nilai asli), `melapor_keliru`, `salah`, `tanpa_angka`, `galat`.
