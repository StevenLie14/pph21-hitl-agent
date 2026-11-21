# Backtest temporal tingkat agent

Model: default (azure), 2026-11-18T11:57:20, ulangan 3.

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
| u2009 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 2, tanpa_angka 1 | benar 3 | ingatan 3 |
| u2013 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 2, tanpa_angka 1 | benar 3 | ingatan 3 |
| u2015 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 1, angka_lama_dengan_catatan 1, angka_lama_diam 1 | benar 3 | ingatan 3 |
| u2016 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 3 | benar 3 | ingatan 3 |
| u2022 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 2, angka_lama_diam 1 | benar 3 | ingatan 3 |
| u2024 | angka_baru_tanpa_lapor 1, tanpa_angka 2 | angka_baru_tanpa_lapor 2, tanpa_angka 1 | angka_baru_tanpa_lapor 3 | benar 1, tanpa_angka 2 | ingatan 2, tanpa_angka 1 |
| u2016p | angka_baru_tanpa_lapor 2, tanpa_angka 1 | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 2, tanpa_angka 1 | benar 3 | ingatan 3 |
| u2022p | angka_baru_tanpa_lapor 3 | angka_baru_tanpa_lapor 2, tanpa_angka 1 | angka_baru_tanpa_lapor 3 | benar 3 | - |
| u2010f | - | - | - | benar 3 | ingatan 2, tanpa_angka 1 |
| u2011f | - | - | - | benar 3 | ingatan 3 |

## Ringkasan (kasus lima fase)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| basi_hilang | 24 | angka_baru_tanpa_lapor 21, tanpa_angka 3 | 0 | 0 | 0 | 3.9 | 1 |
| basi_lanjutan | 24 | angka_baru_tanpa_lapor 22, tanpa_angka 2 | 0 | 0 | 0 | 4.4 | 1 |
| sadar | 24 | angka_baru_tanpa_lapor 18, angka_lama_dengan_catatan 1, angka_lama_diam 2, tanpa_angka 3 | 0 | 6 | 0 | 5.0 | 1 |
| teradaptasi_asli | 24 | benar 22, tanpa_angka 2 | 0 | 0 | 0 | 3.8 | 1 |
| teradaptasi_ubah | 21 | ingatan 20, tanpa_angka 1 | 0 | 0 | 0 | 4.0 | 1 |

## Ringkasan kasus sebagian (hanya fase teradaptasi)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| teradaptasi_asli | 6 | benar 6 | 0 | 0 | 0 | 3.3 | 1 |
| teradaptasi_ubah | 6 | ingatan 5, tanpa_angka 1 | 0 | 0 | 0 | 3.2 | 1 |

Token LLM masuk / keluar: 15006 / 28482 (220.8 keluar per run).

Label hasil: `melapor` (report_possibly_stale tercatat, tanpa angka), `melapor_dengan_angka`, `angka_lama_diam` (menghitung dengan nilai lama tanpa melapor), `angka_lama_dengan_catatan` (sama, tetapi menyebut klaim pengguna), `angka_baru_tanpa_lapor` (angka dari ingatan atau nilai pengguna), `benar`, `ingatan` (varian x1,2 dijawab dengan nilai asli), `melapor_keliru`, `salah`, `tanpa_angka`, `galat`.
