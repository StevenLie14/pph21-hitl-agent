# LLM menghitung PPh 21 sendiri (azure:gpt-6-luna, 28 kasus, 3 run per kondisi)

| kondisi | benar (selisih <= Rp1) | dalam 1% | tanpa angka | median selisih yang salah | kasus benar di semua run | kasus tidak stabil | token rata-rata | jalan kode rata-rata |
|---|---|---|---|---|---|---|---|---|
| tanpa_data | 57/84 | 57/84 | 0 | Rp525,000 | 14/28 | 9 | 1,075 | 0.0 |
| dengan_tabel | 58/84 | 58/84 | 0 | Rp525,000 | 17/28 | 5 | 4,472 | 0.0 |
| dengan_kode | 64/84 | 64/84 | 5 | Rp1,875,000 | 18/28 | 6 | 10,885 | 1.49 |

Acuan: mesin hitung deterministik pada argumen yang diharapkan; kebenaran mesin sendiri dari uji emas contoh lampiran resmi, jadi angka di sini mengukur selisih LLM terhadap mesin.
