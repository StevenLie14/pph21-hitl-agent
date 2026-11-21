# LLM menghitung PPh 21 sendiri (azure:gpt-6-luna, 52 kasus, 3 run per kondisi)

| kondisi | benar (selisih <= Rp1) | dalam 1% | tanpa angka | median selisih yang salah | kasus benar di semua run | kasus tidak stabil | token rata-rata | jalan kode rata-rata |
|---|---|---|---|---|---|---|---|---|
| tanpa_data | 25/156 | 25/156 | 0 | Rp1,200,000 | 8/52 | 1 | 297 | 0.0 |
| dengan_tabel | 38/156 | 38/156 | 0 | Rp1,500,000 | 10/52 | 7 | 3,844 | 0.0 |
| dengan_kode | 77/156 | 77/156 | 0 | Rp600,000 | 12/52 | 24 | 7,585 | 0.9 |

Acuan: mesin hitung deterministik pada argumen yang diharapkan; kebenaran mesin sendiri dari uji emas contoh lampiran resmi, jadi angka di sini mengukur selisih LLM terhadap mesin.
