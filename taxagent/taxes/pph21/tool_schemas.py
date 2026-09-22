from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .calc.rates import default_year, load_regulations

TAHUN_DEFAULT = default_year()


def _kutipan_status():
    return Field(
        "",
        description="Potongan kalimat PENGGUNA yang menyebut status kawin/tanggungan atau kode PTKP, "
        "disalin persis (mis. 'menikah, anak 2' atau 'TK/0'). Jangan mengarang; bila pengguna tidak "
        "menyebutnya, jangan memanggil tool ini dan tanyakan statusnya.",
    )


def _fasilitas_ikn():
    return Field(
        False,
        description="True HANYA bila pengguna menyebut pegawai bekerja di Ibu Kota Nusantara (IKN) pada pemberi "
        "kerja yang memanfaatkan fasilitas PPh 21 ditanggung pemerintah. PPh dihitung biasa lalu seluruhnya "
        "ditanggung pemerintah (tidak dipotong dari gaji). Berlaku sampai 2035; wajib ber-NPWP.",
    )


class _Dasar(BaseModel):
    tahun_pajak: int = Field(
        TAHUN_DEFAULT,
        description="Tahun pajak, misalnya 2025. Menentukan tabel tarif yang dipakai.",
    )


class KomponenArgs(_Dasar):
    gaji_pokok: float = Field(0, description="Gaji atau upah pokok.")
    tunjangan_tetap: float = Field(
        0, description="Tunjangan yang dibayar rutin dan tidak dikaitkan kehadiran, misalnya tunjangan jabatan."
    )
    tunjangan_tidak_tetap: float = Field(
        0, description="Tunjangan yang besarnya berubah, misalnya tunjangan transport atau makan harian."
    )
    lembur: float = Field(0, description="Upah lembur.")
    bonus_thr_komisi: float = Field(0, description="Bonus, THR, gratifikasi, jasa produksi, atau komisi.")
    tunjangan_pph: float = Field(
        0, description="Tunjangan PPh pada skema gross-up. Merupakan penghasilan bagi pegawai."
    )
    premi_jkk_dibayar_perusahaan: float = Field(
        0, description="Premi Jaminan Kecelakaan Kerja yang dibayar pemberi kerja. MENAMBAH penghasilan bruto."
    )
    premi_jkm_dibayar_perusahaan: float = Field(
        0, description="Premi Jaminan Kematian yang dibayar pemberi kerja. MENAMBAH penghasilan bruto."
    )
    premi_bpjs_kesehatan_dibayar_perusahaan: float = Field(
        0, description="Iuran BPJS Kesehatan yang dibayar pemberi kerja (umumnya 4%). MENAMBAH penghasilan bruto."
    )
    natura_kena_pajak: float = Field(
        0, description="Nilai natura atau kenikmatan yang merupakan objek pajak."
    )
    penghasilan_lain: float = Field(0, description="Penghasilan teratur lain yang belum tercakup di atas.")

    iuran_jht_dibayar_perusahaan: float = Field(
        0, description="Iuran JHT yang dibayar pemberi kerja (umumnya 3,7%). TIDAK menambah penghasilan bruto."
    )
    iuran_jp_dibayar_perusahaan: float = Field(
        0, description="Iuran Jaminan Pensiun yang dibayar pemberi kerja (umumnya 2%). TIDAK menambah penghasilan bruto."
    )

    iuran_pensiun_dibayar_pegawai: float = Field(
        0, description="Iuran ke dana pensiun yang dibayar sendiri oleh pegawai. Merupakan PENGURANG."
    )
    iuran_jht_dibayar_pegawai: float = Field(
        0, description="Iuran JHT yang dipotong dari gaji pegawai (umumnya 2%). Merupakan PENGURANG."
    )
    iuran_jp_dibayar_pegawai: float = Field(
        0, description="Iuran Jaminan Pensiun yang dipotong dari gaji pegawai (umumnya 1%). Merupakan PENGURANG."
    )
    zakat_via_pemberi_kerja: float = Field(
        0, description="Zakat atau sumbangan keagamaan wajib yang dibayarkan melalui pemberi kerja. Merupakan PENGURANG."
    )

    iuran_bpjs_kesehatan_dibayar_pegawai: float = Field(
        0, description="Iuran BPJS Kesehatan yang dipotong dari gaji pegawai (umumnya 1%). BUKAN pengurang."
    )

    status_ptkp: str = Field(
        ...,
        description="Kode status PTKP: TK/0, TK/1, TK/2, TK/3, K/0, K/1, K/2, atau K/3. "
        "Bila pengguna hanya menyebut status kawin dan jumlah anak, panggil lookup_ptkp lebih dulu.",
    )
    kutipan_status_ptkp: str = _kutipan_status()
    punya_npwp: bool = Field(
        True,
        description="True bila penerima penghasilan memiliki NPWP atau NIK yang telah dipadankan. "
        "Bila False, dikenakan tarif 20% lebih tinggi.",
    )


class BulananArgs(KomponenArgs):
    masa_pajak: int = Field(
        ..., description="Masa pajak 1 sampai 11 (Januari sampai November). Untuk Desember gunakan tool masa pajak terakhir."
    )
    gross_up: bool = Field(
        False,
        description="True bila PPh 21 ditanggung penuh pemberi kerja (full gross-up): tool menghitung "
        "sendiri tunjangan PPh-nya. Bila True, tunjangan_pph harus 0.",
    )
    fasilitas_ikn: bool = _fasilitas_ikn()


_DESKRIPSI_PER_BULAN = (
    "True bila nilai penghasilan, iuran, dan zakat yang diisi adalah jumlah SEBULAN yang sama "
    "setiap bulan; tool sendiri yang mengalikannya dengan bulan_masa_perolehan. JANGAN mengalikan "
    "sendiri. False bila yang diisi sudah jumlah total selama bulan_masa_perolehan."
)
_DESKRIPSI_BULAN = (
    "Jumlah bulan penghasilan diterima dari pemberi kerja/pembayar ini dalam tahun pajak, dihitung "
    "dari periode yang disebut pengguna (mis. Januari-Agustus = 8, mulai September = 4). 12 bila "
    "setahun penuh. Menentukan batas biaya jabatan/biaya pensiun."
)


_DESKRIPSI_DISETAHUNKAN = (
    "True HANYA bila kewajiban pajak subjektif mulai setelah Januari atau berakhir sebelum "
    "Desember: WNA baru datang/menetap, meninggal dunia, atau meninggalkan Indonesia selamanya. "
    "False untuk yang sekadar mulai/berhenti bekerja atau mulai pensiun tapi tetap tinggal di "
    "Indonesia, dan untuk setahun penuh."
)


class TahunanArgs(KomponenArgs):
    bulan_masa_perolehan: int = Field(12, description=_DESKRIPSI_BULAN)
    nilai_per_bulan: bool = Field(False, description=_DESKRIPSI_PER_BULAN)
    disetahunkan: bool = Field(
        False,
        description=_DESKRIPSI_DISETAHUNKAN,
    )
    neto_pemberi_kerja_sebelumnya: float = Field(
        0,
        description="HANYA bila pegawai PINDAH KERJA dan menyebut angka dari bukti potong pemberi "
        "kerja LAMA: penghasilan neto dari bukti potong itu. JANGAN isi gaji/penghasilan dari "
        "pemberi kerja yang sedang menghitung (itu masuk gaji_pokok dan komponen lain). "
        "0 bila tidak pindah kerja.",
    )
    fasilitas_ikn: bool = _fasilitas_ikn()


class MasaTerakhirArgs(TahunanArgs):
    pph_sudah_dipotong: float = Field(
        ..., description="Total PPh 21 yang sudah dipotong pada masa-masa pajak sebelumnya di pemberi kerja ini. "
        "Isi 0 HANYA bila pengguna menyebut belum ada potongan; bila tidak disebut, tanyakan dulu.",
    )
    pph_sudah_dipotong_ter_sama: bool = Field(
        False,
        description="True bila pengguna tidak tahu jumlah PPh yang sudah dipotong dan penghasilannya sama setiap "
        "bulan: tool memperkirakan potongan masa-masa sebelumnya = TER bulanan atas penghasilan sebulan x "
        "(bulan_masa_perolehan - 1). Wajib nilai_per_bulan=true; pph_sudah_dipotong diisi 0.",
    )
    masa_pajak: int = Field(12, description="Masa pajak terakhir, umumnya 12 (Desember).")
    gross_up: bool = Field(
        False,
        description="True bila PPh 21 ditanggung penuh pemberi kerja sepanjang tahun (full gross-up): "
        "tool menghitung tunjangan PPh masa terakhir sendiri. Isi pph_sudah_dipotong dengan "
        "tunjangan PPh Januari-November (= PPh yang sudah dipotong) dan tunjangan_pph 0.",
    )
    pph_dipotong_pemberi_kerja_sebelumnya: float = Field(
        0,
        description="Untuk pegawai yang pindah kerja di tahun pajak yang sama: PPh 21 yang SUDAH "
        "dipotong oleh pemberi kerja sebelumnya, dari Form 1721-A1. Diperhitungkan sebagai kredit "
        "pajak. Kosongkan (0) bila tidak pindah kerja.",
    )


class PensiunanArgs(_Dasar):
    uang_pensiun: float = Field(
        ..., description="Uang pensiun berkala yang dibayarkan dana pensiun/pembayar pensiun, rupiah penuh."
    )
    penghasilan_lain: float = Field(
        0,
        description="Penghasilan lain dari pembayar pensiun yang sama, misalnya uang pensiun "
        "ketiga belas, THR, atau tunjangan lain. MENAMBAH penghasilan bruto.",
    )
    status_ptkp: str = Field(
        ...,
        description="Kode status PTKP: TK/0 sampai K/3. Bila pengguna hanya menyebut status "
        "kawin dan jumlah tanggungan, panggil lookup_ptkp lebih dulu.",
    )
    kutipan_status_ptkp: str = _kutipan_status()
    punya_npwp: bool = Field(True, description="True bila pensiunan memiliki NPWP. Bila False, tarif 20% lebih tinggi.")


class PensiunanBulananArgs(PensiunanArgs):
    masa_pajak: int = Field(
        ..., description="Masa pajak 1 sampai 11. Untuk masa pajak terakhir gunakan tool masa pajak terakhir pensiunan."
    )


class PensiunanTahunanArgs(PensiunanArgs):
    zakat_via_pembayar_pensiun: float = Field(
        0,
        description="Zakat atau sumbangan keagamaan wajib setahun yang dibayarkan melalui "
        "pembayar uang pensiun. Merupakan PENGURANG.",
    )
    bulan_masa_perolehan: int = Field(12, description=_DESKRIPSI_BULAN)
    nilai_per_bulan: bool = Field(False, description=_DESKRIPSI_PER_BULAN)
    disetahunkan: bool = Field(
        False,
        description=_DESKRIPSI_DISETAHUNKAN,
    )
    neto_pemberi_sebelumnya: float = Field(
        0,
        description="HANYA penghasilan neto dari bukti potong pemberi kerja/pembayar pensiun LAIN "
        "di tahun pajak yang sama, misalnya gaji sebelum mulai pensiun. JANGAN isi uang pensiun "
        "dari pembayar ini (itu masuk uang_pensiun). 0 bila tidak ada.",
    )


class PensiunanMasaTerakhirArgs(PensiunanTahunanArgs):
    pph_sudah_dipotong: float = Field(
        ..., description="Total PPh 21 yang sudah dipotong pembayar pensiun ini pada masa-masa pajak sebelumnya."
    )
    masa_pajak: int = Field(12, description="Masa pajak terakhir, umumnya 12 (Desember).")
    pph_dipotong_pemberi_sebelumnya: float = Field(
        0,
        description="PPh 21 terutang di pemberi kerja atau pembayar pensiun sebelumnya pada tahun "
        "pajak yang sama, dari bukti pemotongannya. Diperhitungkan sebagai kredit.",
    )


class NaturaArgs(_Dasar):
    masa_pajak: int = Field(0, description="Masa pajak 1-12 (informasi saja; 0 bila tidak disebut).")
    makanan_di_tempat_kerja: float = Field(0, description="Makanan/minuman yang disediakan di tempat kerja bagi seluruh pegawai.")
    kupon_makanan: float = Field(
        0, description="Kupon/penggantian makanan sebulan bagi pegawai pemasaran, transportasi, atau dinas luar."
    )
    nilai_makanan_kantor_sebulan: float = Field(
        0, description="Nilai makanan di kantor per pegawai sebulan; menaikkan batas kupon bila lebih dari Rp2.000.000."
    )
    bingkisan_hari_raya: float = Field(
        0, description="Bingkisan hari raya keagamaan (Idulfitri, Natal, Nyepi, Waisak, Imlek) bagi seluruh pegawai."
    )
    bingkisan_lain: float = Field(0, description="Bingkisan lain (ulang tahun perusahaan, apresiasi kinerja, dst.) di masa ini.")
    bingkisan_lain_sebelumnya_tahun_ini: float = Field(
        0, description="Total bingkisan lain yang SUDAH diterima sebelum masa ini di tahun yang sama."
    )
    peralatan_kerja: float = Field(0, description="Komputer, laptop, telepon seluler, pulsa, internet penunjang pekerjaan.")
    kesehatan_akibat_kerja: float = Field(
        0, description="Layanan kesehatan karena kecelakaan kerja, penyakit akibat kerja, atau kedaruratan."
    )
    fasilitas_olahraga: float = Field(
        0, description="Fasilitas olahraga di masa ini (golf, pacuan kuda, balap perahu, terbang layang, otomotif isi ke natura_lain)."
    )
    olahraga_sebelumnya_tahun_ini: float = Field(
        0, description="Total fasilitas olahraga yang SUDAH diterima sebelum masa ini di tahun yang sama."
    )
    tempat_tinggal_komunal: float = Field(0, description="Mes, asrama, pondokan, barak yang dipakai bersama.")
    tempat_tinggal_individual: float = Field(0, description="Apartemen/rumah untuk perseorangan, nilai sebulan.")
    kendaraan: float = Field(0, description="Nilai fasilitas kendaraan dari pemberi kerja di masa ini.")
    pegawai_punya_penyertaan_modal: bool = Field(
        False, description="True bila pegawai punya penyertaan modal pada pemberi kerja (fasilitas kendaraan jadi kena pajak)."
    )
    rata_rata_bruto_12_bulan: float = Field(
        0, description="Rata-rata penghasilan bruto sebulan selama 12 bulan terakhir dari pemberi kerja (untuk syarat kendaraan)."
    )
    iuran_dana_pensiun_ditanggung: float = Field(0, description="Iuran dana pensiun (disahkan OJK) yang ditanggung pemberi kerja.")
    fasilitas_peribadatan: float = Field(0, description="Musala, masjid, kapel, pura dan sejenisnya.")
    wajib_untuk_pekerjaan: float = Field(
        0, description="Seragam, alat keselamatan kerja, antar jemput, penginapan awak kapal, penanganan pandemi/bencana."
    )
    natura_lain: float = Field(0, description="Natura/kenikmatan lain yang tidak termasuk jenis di atas; kena pajak penuh.")


class PtkpArgs(_Dasar):
    kawin: bool = Field(..., description="True bila berstatus kawin.")
    jumlah_tanggungan: int = Field(
        ..., description="Jumlah anggota keluarga yang menjadi tanggungan sepenuhnya. Maksimal 3 yang diperhitungkan."
    )
    kutipan_status_ptkp: str = _kutipan_status()


class TerArgs(_Dasar):
    status_ptkp: str = Field(..., description="Kode status PTKP, misalnya K/1.")
    penghasilan_bruto_sebulan: float = Field(..., description="Penghasilan bruto sebulan dalam rupiah penuh.")


class TidakTetapArgs(_Dasar):
    upah_per_periode: float = Field(..., description="Upah untuk satu periode pembayaran, dalam rupiah penuh.")
    skema: str = Field(
        ..., description="Salah satu: harian, mingguan, satuan, borongan, atau bulanan."
    )
    jumlah_hari: int = Field(
        1, description="Jumlah hari yang dicakup pembayaran ini. Dipakai untuk memperoleh upah sehari."
    )
    status_ptkp: str = Field(
        "", description="Wajib diisi hanya untuk skema bulanan, karena menentukan kategori TER."
    )
    kutipan_status_ptkp: str = _kutipan_status()
    punya_npwp: bool = Field(True, description="True bila penerima memiliki NPWP.")
    fasilitas_ikn: bool = _fasilitas_ikn()


class BukanPegawaiArgs(_Dasar):
    penghasilan_bruto: float = Field(
        ..., description="Seluruh imbalan yang dibayarkan pada masa pajak ini, dalam rupiah penuh."
    )
    pembayaran_dikecualikan: float = Field(
        0,
        description="Untuk jasa selain katering: upah tenaga kerja yang dipekerjakan penerima, pembelian "
        "material terkait jasa, dan pembayaran ke pihak ketiga, yang dibuktikan kontrak/faktur. "
        "Dikurangkan dari bruto sebelum DPP 50%. Isi 0 bila tidak ada.",
    )
    jasa_katering: bool = Field(
        False, description="True untuk jasa katering; pembayaran dikecualikan tidak berlaku untuk katering."
    )
    jenis_jasa: str = Field(
        "",
        description="Hanya menentukan kode objek pajak bukti potong, tidak mengubah angka. Salah satu: "
        "distributor_mlm, agen_asuransi, penjaja_barang, tenaga_ahli (pengacara, akuntan, arsitek, dokter, "
        "konsultan, notaris, PPAT, penilai, aktuaris), penasihat_pengajar (juga pelatih, penceramah, moderator), "
        "pengarang_peneliti (juga penerjemah), agen_iklan, pengawas_proyek, perantara, seniman_influencer "
        "(pemain musik, MC, penyanyi, bintang film, model, pembuat konten), olahragawan, atau pemberi_jasa_lain "
        "(hanya sisa yang tidak masuk kategori di atas, mis. teknisi atau jasa perbaikan; konsultan selalu "
        "tenaga_ahli). Kosongkan bila tidak jelas.",
    )
    punya_npwp: bool = Field(True, description="True bila penerima memiliki NPWP.")


class DewanKomisarisArgs(_Dasar):
    penghasilan_bruto: float = Field(
        ..., description="Honorarium/penghasilan tidak teratur yang diterima, dalam rupiah penuh. "
        "TIDAK dikurangi 50% seperti bukan pegawai; dasar pengenaan pajak adalah bruto penuh."
    )
    status_ptkp: str = Field(..., description="Kode status PTKP, misalnya TK/0. Menentukan kategori TER.")
    kutipan_status_ptkp: str = _kutipan_status()
    punya_npwp: bool = Field(True, description="True bila penerima memiliki NPWP.")


class Pasal17LangsungArgs(_Dasar):
    jenis: str = Field(
        ...,
        description="Salah satu: peserta_kegiatan (hadiah/penghargaan lomba atau kegiatan), "
        "peserta_pensiun_pegawai (penarikan uang manfaat pensiun oleh pegawai aktif), atau "
        "mantan_pegawai (jasa produksi/tantiem/gratifikasi/bonus setelah berhenti bekerja).",
    )
    jenis_kegiatan: str = Field(
        "",
        description="Hanya untuk jenis peserta_kegiatan, menentukan kode objek pajak (tidak mengubah angka). "
        "Salah satu: rapat_seminar (rapat, konferensi, sidang, kunjungan kerja, seminar, lokakarya, "
        "pertunjukan), panitia, pendidikan_pelatihan (juga magang), perlombaan, atau lainnya. Kosongkan bila "
        "tidak jelas.",
    )
    penghasilan_bruto: float = Field(
        ..., description="Jumlah bruto yang diterima, dalam rupiah penuh. TIDAK dikurangi PTKP atau apa pun."
    )
    punya_npwp: bool = Field(True, description="True bila penerima memiliki NPWP.")


class FinalArgs(_Dasar):
    jenis: str = Field(
        ..., description="Salah satu: pesangon, manfaat_pensiun, atau honorarium_pns."
    )
    jumlah_bruto: float = Field(..., description="Jumlah bruto yang dibayarkan, dalam rupiah penuh.")
    golongan: str = Field(
        "", description="Golongan kepangkatan (I, II, III, atau IV). Wajib hanya untuk jenis honorarium_pns."
    )
    tahun_pembayaran_ke: int = Field(
        1,
        description="Untuk pesangon dan manfaat_pensiun (termasuk THT/JHT): tahun kalender ke berapa pembayaran "
        "ini sejak pembayaran pertama. 1 atau 2 = final (tarif berlapis); 3 atau lebih = tidak final, tarif "
        "Pasal 17 atas jumlah bruto yang dibayar pada tahun kalender itu.",
    )
    dibayar_sebelumnya_tahun_ini: float = Field(
        0,
        description="Hanya bila tahun_pembayaran_ke >= 3: jumlah bruto yang sudah dibayar lebih dulu pada tahun "
        "kalender yang sama (tarif Pasal 17 berlaku kumulatif per tahun kalender). 0 bila ini pembayaran pertama "
        "tahun itu.",
    )
    punya_npwp: bool = Field(
        True, description="Hanya berpengaruh bila tahun_pembayaran_ke >= 3: tanpa NPWP tarif 20% lebih tinggi."
    )


class Pph26Args(_Dasar):
    penghasilan_bruto: float = Field(..., description="Jumlah bruto yang dibayarkan, dalam rupiah penuh.")
    negara_domisili: str = Field("", description="Negara domisili penerima penghasilan.")
    tarif_p3b_persen: float = Field(
        -1, description="Tarif P3B dalam persen. Isi -1 bila tidak ada atau tidak diketahui."
    )
    ada_surat_keterangan_domisili: bool = Field(
        False, description="True bila penerima dapat menunjukkan Surat Keterangan Domisili yang sah."
    )


_REGULASI = load_regulations()
TopikRegulasi = Literal[tuple(_REGULASI)]


class DasarHukumArgs(BaseModel):
    topic: TopikRegulasi = Field(
        ...,
        description="Kunci topik di peta regulasi: " + ", ".join(_REGULASI)
        + ". Bila pertanyaannya tidak persis salah satu topik ini (mis. insentif PPh 21 DTP PMK 10/2025, aturan di "
        "luar PPh 21), JANGAN memilih topik yang mirip: pakai search_faq, find_regulation, atau search_text.",
    )


class TahunArgs(_Dasar):
    pass
