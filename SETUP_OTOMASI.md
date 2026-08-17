# Panduan Setup — Otomasi Scraping IDX + Dashboard Bandarmology

File baru/diubah yang ditambahkan di atas repo `nichsedge/idx-bei`:

```
python/src/idx/pipelines/bandarmology.py   # skor accumulation/distribution
python/src/idx/pipelines/website.py        # bundel JSON ringan utk dashboard
python/src/idx/pipelines/daily.py          # (diedit) auto-panggil bandarmology + website
python/cli.py                              # (diedit) tambah command `bandar`
site/index.html                            # dashboard statis
.github/workflows/idx-daily.yml            # otomasi harian: scrape → skor → deploy
.gitignore                                 # (diedit) data/timeseries/ tidak lagi di-ignore
```

## 1. Push ke repo GitHub Anda (fork atau repo baru)

```bash
git init  # jika belum
git remote add origin https://github.com/<username>/<repo>.git
git add .
git commit -m "feat: automated daily pipeline + bandarmology dashboard"
git push -u origin main
```

## 2. Backfill histori dulu (WAJIB, sekali di awal)

Skor bandarmology butuh histori 5–20 hari bursa untuk hitung z-score. Tanpa ini, dashboard akan kosong.

```bash
cd python
uv sync
uv run python cli.py backfill --start 20260701 --end 20260814 --type all
```

Sesuaikan tanggal (format `YYYYMMDD`). Commit hasilnya:

```bash
git add ../data
git commit -m "chore: initial historical backfill"
git push
```

## 3. Aktifkan GitHub Pages

Di repo GitHub Anda: **Settings → Pages → Source: "GitHub Actions"**. Tidak perlu setting lain — workflow yang sudah dibuat akan build & deploy folder `site/` otomatis.

## 4. Jalankan sekali secara manual untuk cek

Di tab **Actions** repo Anda → pilih workflow **"IDX Daily Scrape & Dashboard Deploy"** → **Run workflow**. Setelah selesai (~1-3 menit), buka URL Pages yang muncul di summary run tersebut.

## 5. Selanjutnya, semua otomatis

- Jadwal: setiap hari bursa, **17:15 WIB**, workflow scrape data hari itu, hitung skor, commit ke repo, dan re-deploy dashboard.
- Tidak perlu server, cron pribadi, atau maintenance manual.

## Command lokal yang tersedia

```bash
uv run python cli.py trading         # scrape OHLCV + broker + index (snapshot hari ini)
uv run python cli.py daily           # full pipeline: scrape + skor + bundel website
uv run python cli.py bandar          # cuma hitung & tampilkan skor bandarmology hari ini
uv run python cli.py backfill --start ... --end ...
uv run python cli.py parquet         # export ke Parquet untuk analisis lanjutan (pandas dsb.)
```

## Batasan yang perlu Anda tahu

- **Broker summary** dari API publik IDX itu **agregat market-wide** (per broker, seluruh pasar), **bukan** per-saham. Tabel "broker mana beli saham X" yang biasa dipakai bandarmology klasik **tidak tersedia gratis** — itu hanya ada di IDX Data Services (berbayar) atau terminal broker premium.
- **Data tick-by-tick / running trade / done detail** per saham juga **tidak** disediakan API publik ini. Sama seperti di atas, itu produk berbayar.
- Skor `AccumulationScore` di dashboard adalah **proxy heuristik** dari data publik (anomali volume/frekuensi, foreign flow, imbalance bid/offer) — bukan sinyal broker asli, dan **bukan nasihat investasi**.
- Kalau Anda punya akses resmi ke data broker-per-saham atau feed tick (mis. langganan IDX Data Services, atau API vendor lain yang Anda berlangganan), saya bisa bantu buat konektor tambahan untuk menggabungkannya ke pipeline ini.
