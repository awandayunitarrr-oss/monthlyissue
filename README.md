# Motorcycle Issue Dashboard

Dashboard rekap issue motor dari **Iwan Banaran**, **Pertamax7**, dan **TMC Blog**,
di-update otomatis 2× sebulan (tanggal 15 dan hari terakhir bulan, 23:30 WIB).

## Cara kerja

| Bagian | File | Fungsi |
| --- | --- | --- |
| Scraper | `scraper/fetch_issues.py` | Ambil artikel per periode (RSS → sitemap → halaman depan), beri tag merek & kategori |
| Konfigurasi | `scraper/config.json` | Daftar sumber, kata kunci merek & kategori |
| Data | `docs/data/periods/YYYY-MM-H1.json` / `H2.json` | Satu file per periode (H1 = tgl 1–15, H2 = tgl 16–akhir) |
| Dashboard | `docs/index.html` | Halaman statis, membaca `docs/data/` |
| Jadwal | `.github/workflows/update-issues.yml` | Menjalankan scraper, commit data, deploy ke GitHub Pages |

## Aktivasi (sekali saja)

1. Merge branch ini ke `main` (jadwal GitHub Actions hanya jalan dari default branch).
2. **Settings → Pages → Source: GitHub Actions**.
3. **Settings → Actions → General → Workflow permissions: Read and write**.
4. **Actions → Update Motorcycle Issue → Run workflow** untuk percobaan pertama
   (isi periode, mis. `2026-11-H1`, atau kosongkan).

## Menjalankan manual

```bash
pip install -r scraper/requirements.txt
python scraper/fetch_issues.py --period 2026-11-H1
python -m http.server -d docs 8000   # buka http://localhost:8000
```

## Kurasi manual

Di file periode, tiap artikel boleh diberi:

- `"highlight": true` — tandai ★ sebagai issue pilihan untuk deck
- `"locked": true` — judul/ringkasan/tag yang sudah diedit tidak ditimpa saat update berikutnya
- `"note": "..."` — catatan bebas

Tambah merek/kategori baru cukup lewat `scraper/config.json`.
