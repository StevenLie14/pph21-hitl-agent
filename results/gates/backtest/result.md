# Backtest temporal: sistem dibekukan sebelum setiap perubahan nyata

Dibuat oleh `pph21 draft-backtest`. Model LLM: azure:gpt-6-luna, prompt draf-llm-v3-2026-11-16-teks-utuh. Peristiwa: `taxagent/taxes/pph21/data/peristiwa_backtest.yaml`; label nilai: `draf_label.yaml`.

## 1. Per peristiwa

| peristiwa | tanggal | terdeteksi | varian | harapan | keputusan | sesuai | salah lolos | gerbang menahan | berlaku terbaca/label | nilai lama tidak diketahui |
|---|---|---|---|---|---|---|---|---|---|---|
| KMK 564 Tahun 2004 | 2004-11-29 | ya | asli | siap | tahan | **tidak** | 0 | G1, G4 | 2005/2005 | - |
| KMK 564 Tahun 2004 | 2004-11-29 | ya | ubah | siap | tahan | **tidak** | 0 | G1, G4 | 2005/2005 | - |
| PMK 10 Tahun 2005 | 2005-01-31 | ya | asli | siap | tahan | **tidak** | 0 | G1 | 2005/2005 | ter_harian |
| PMK 10 Tahun 2005 | 2005-01-31 | ya | ubah | siap | tahan | **tidak** | 0 | G1 | 2005/2005 | ter_harian |
| PMK 137 Tahun 2005 | 2005-12-30 | ya | asli | siap | tahan | **tidak** | 0 | G5 | 2006/2006 | - |
| PMK 137 Tahun 2005 | 2005-12-30 | ya | ubah | siap | tahan | **tidak** | 0 | G5 | 2006/2006 | - |
| PMK 138 Tahun 2005 | 2005-12-30 | ya | asli | siap | tahan | **tidak** | 0 | G1, G4 | 2006/2006 | - |
| PMK 138 Tahun 2005 | 2005-12-30 | ya | ubah | siap | tahan | **tidak** | 0 | G1, G4 | 2006/2006 | - |
| UU 36 Tahun 2008 | 2008-09-23 | ya | asli | tahan | tahan | ya | 0 | G1, G4, G5, G6 | 2010/2009 | - |
| UU 36 Tahun 2008 | 2008-09-23 | ya | ubah | tahan | tahan | ya | 0 | G1, G3, G4, G5, G6 | 2010/2009 | - |
| PMK 250 Tahun 2008 | 2008-12-31 | ya | asli | siap | tahan | **tidak** | 0 | G1, G4 | 2009/2009 | biaya_jabatan, biaya_pensiun |
| PMK 250 Tahun 2008 | 2008-12-31 | ya | ubah | siap | tahan | **tidak** | 0 | G1, G4 | 2009/2009 | biaya_jabatan, biaya_pensiun |
| PMK 254 Tahun 2008 | 2008-12-31 | ya | asli | siap | siap | ya | 0 | - | 2009/2009 | - |
| PMK 254 Tahun 2008 | 2008-12-31 | ya | ubah | siap | siap | ya | 0 | - | 2009/2009 | - |
| PP 68 Tahun 2009 | 2009-11-16 | ya | asli | tahan | tahan | ya | 0 | G1, G4, G6 | None/None | pph_final_manfaat_pensiun, pph_final_pesangon |
| PP 68 Tahun 2009 | 2009-11-16 | ya | ubah | tahan | tahan | ya | 0 | G1, G4, G6 | None/None | pph_final_manfaat_pensiun, pph_final_pesangon |
| PP 80 Tahun 2010 | 2010-12-20 | ya | asli | siap | tahan | **tidak** | 0 | G1 | 2011/2011 | pph_final_honorarium_pns |
| PP 80 Tahun 2010 | 2010-12-20 | ya | ubah | siap | tahan | **tidak** | 0 | G1 | 2011/2011 | pph_final_honorarium_pns |
| PMK 162 Tahun 2012 | 2012-10-22 | ya | asli | siap | tahan | **tidak** | 0 | G6 | None/2013 | - |
| PMK 162 Tahun 2012 | 2012-10-22 | ya | ubah | siap | tahan | **tidak** | 0 | G6 | None/2013 | - |
| PMK 206 Tahun 2012 | 2012-12-17 | ya | asli | siap | siap | ya | 0 | - | 2013/2013 | - |
| PMK 206 Tahun 2012 | 2012-12-17 | ya | ubah | siap | siap | ya | 0 | - | 2013/2013 | - |
| PMK 122 Tahun 2015 | 2015-06-29 | ya | asli | siap | siap | ya | 0 | - | 2015/2015 | - |
| PMK 122 Tahun 2015 | 2015-06-29 | ya | ubah | siap | siap | ya | 0 | - | 2015/2015 | - |
| PMK 152 Tahun 2015 | 2015-08-06 | ya | asli | tahan | tahan | ya | 0 | G6 | None/None | - |
| PMK 152 Tahun 2015 | 2015-08-06 | ya | ubah | tahan | tahan | ya | 0 | G6 | None/None | - |
| PMK 101 Tahun 2016 | 2016-06-22 | ya | asli | siap | siap | ya | 0 | - | 2016/2016 | - |
| PMK 101 Tahun 2016 | 2016-06-22 | ya | ubah | siap | siap | ya | 0 | - | 2016/2016 | - |
| PMK 102 Tahun 2016 | 2016-06-22 | ya | asli | tahan | tahan | ya | 0 | G6 | None/None | - |
| PMK 102 Tahun 2016 | 2016-06-22 | ya | ubah | tahan | tahan | ya | 0 | G6 | None/None | - |
| UU 7 Tahun 2021 | 2021-10-29 | ya | asli | tahan | tahan | ya | 0 | G1, G6 | None/None | - |
| UU 7 Tahun 2021 | 2021-10-29 | ya | ubah | tahan | tahan | ya | 0 | G1, G6 | None/None | - |
| PP 58 Tahun 2023 | 2023-12-27 | ya | asli | tahan | tahan | ya | 0 | G4, G6, G8 | 2024/2024 | ter_bulanan, ter_harian |
| PP 58 Tahun 2023 | 2023-12-27 | ya | ubah | tahan | dilewati | - | 0 | - | None/2024 | ter_bulanan, ter_harian |
| PMK 168 Tahun 2023 | 2023-12-29 | ya | asli | tahan | tahan | ya | 0 | G1 | 2024/2024 | ter_harian |
| PMK 168 Tahun 2023 | 2023-12-29 | ya | ubah | tahan | tahan | ya | 0 | G1, G4 | 2024/2024 | ter_harian |

## 2. Ringkasan

- **asli**: 18 peristiwa; siap 4 (benar 4), tahan 14, tidak ada perubahan 0, ditolak 0; sesuai harapan 11/18; **salah lolos 0**
- **ubah**: 17 peristiwa; siap 4 (benar 4), tahan 13, tidak ada perubahan 0, ditolak 0; sesuai harapan 10/17; **salah lolos 0**
- LLM pada angka yang dimutasi: dibaca 52, **dari ingatan 0**, lain 1, tidak menjawab 1
- Dokumen yang menulis ulang nilai lama: 6 dokumen; siap 0, salah lolos **0**; keputusan tahan 6
- Kontrol negatif: 7 dokumen; siap 0, salah lolos **0**; keputusan tidak_ada_perubahan 6, tahan 1
- Pembanding pada 48 run (tanpa panggilan LLM tambahan): nilai salah masuk tabel bila draf diterima tanpa gerbang **0**, bila bacaan LLM diterima langsung **1**, dengan G1-G8 **0**
- Deteksi pemantau (aturan judul ATAU LLM cuplikan kata kunci): 18/18 peristiwa
- Sumber teks (urutan sistem terpasang: JDIH andal, pajak.go.id, JDIH perlu_dicek): jdih 21, pajak.go.id 11
- Tabel lampiran: PDF JDIH lokal: OCR kotak + LLM vision; dinilai terpisah (`tabel_ocr`, `tabel_visi`), ekstraktor teks dinilai tanpa daun tabel

## 3. Ekstraksi per angka (peristiwa)

| varian | ekstraktor | benar | salah | terlewat | presisi | recall |
|---|---|---|---|---|---|---|
| asli | det | 56 | 0 | 27 | 100.0% | 67.5% |
| asli | llm | 83 | 4 | 0 | 95.4% | 100.0% |
| asli | sepakat | 56 | 0 | 27 | 100.0% | 67.5% |
| asli | tabel_ocr | 254 | 0 | 0 | 100.0% | 100.0% |
| asli | tabel_visi | 254 | 0 | 0 | 100.0% | 100.0% |
| ubah | det | 56 | 0 | 27 | 100.0% | 67.5% |
| ubah | llm | 81 | 4 | 1 | 95.3% | 98.8% |
| ubah | sepakat | 54 | 0 | 29 | 100.0% | 65.1% |

## 4. Kasus yang perlu dibaca

- KMK 564 Tahun 2004 (asli): tahan; ditandai Fase 1 tetapi angkanya tidak terbaca: ptkp; ptkp.wajib_pajak_sendiri: LLM membaca 12000000 (tabel 2880000), ekstraktor deterministik tidak membacanya; ptkp.tambahan_kawin: LLM membaca 1200000 (tabel 1440000), ekstraktor deterministik tidak membacanya
- KMK 564 Tahun 2004 (ubah): tahan; ditandai Fase 1 tetapi angkanya tidak terbaca: ptkp; ptkp.wajib_pajak_sendiri: LLM membaca 14400000 (tabel 2880000), ekstraktor deterministik tidak membacanya
- PMK 10 Tahun 2005 (asli): tahan; ter_harian: struktur berubah (sub-key ['batas_bebas_harian'])
- PMK 10 Tahun 2005 (ubah): tahan; ter_harian: struktur berubah (sub-key ['batas_bebas_harian'])
- PMK 137 Tahun 2005 (asli): tahan; ptkp.wajib_pajak_sendiri=13200000 di luar rentang 20,000,000-200,000,000
- PMK 137 Tahun 2005 (ubah): tahan; ptkp.wajib_pajak_sendiri=15840000 di luar rentang 20,000,000-200,000,000
- PMK 138 Tahun 2005 (asli): tahan; ditandai Fase 1 tetapi angkanya tidak terbaca: ter_harian; ter_harian.batas_bebas_harian: LLM membaca 110000 (tabel 100000), ekstraktor deterministik tidak membacanya
- PMK 138 Tahun 2005 (ubah): tahan; ditandai Fase 1 tetapi angkanya tidak terbaca: ter_harian; ter_harian.batas_bebas_harian: LLM membaca 132000 (tabel 100000), ekstraktor deterministik tidak membacanya
- PMK 250 Tahun 2008 (asli): tahan; ditandai Fase 1 tetapi angkanya tidak terbaca: biaya_jabatan, biaya_pensiun; biaya_jabatan.persen: LLM membaca 5, field ini tidak ada di tabel (struktur berubah?); biaya_jabatan.maksimal_setahun: LLM membaca 6000000, field ini tidak ada di tabel (struktur berubah?)
- PMK 250 Tahun 2008 (ubah): tahan; ditandai Fase 1 tetapi angkanya tidak terbaca: biaya_jabatan, biaya_pensiun; biaya_jabatan.persen: LLM membaca 6, field ini tidak ada di tabel (struktur berubah?); biaya_jabatan.maksimal_setahun: LLM membaca 7200000, field ini tidak ada di tabel (struktur berubah?)
- PP 80 Tahun 2010 (asli): tahan; pph_final_honorarium_pns: struktur berubah (sub-key ['I', 'II', 'III', 'IV'])
- PP 80 Tahun 2010 (ubah): tahan; pph_final_honorarium_pns: struktur berubah (sub-key ['I', 'II', 'III', 'IV'])
- PMK 162 Tahun 2012 (asli): tahan; s: mulai berlaku 2026-10-22 (tengah tahun)
- PMK 162 Tahun 2012 (ubah): tahan; s: mulai berlaku 2026-10-22 (tengah tahun)
