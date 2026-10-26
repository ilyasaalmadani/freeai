# FreeAI — CLI coding dan API AI gratis

CLI coding dan chat untuk macOS, pencari endpoint AI gratis, dan integrasi FreeLLMAPI.
Python 3.10+; CLI tidak memerlukan pip atau paket Python tambahan. FreeLLMAPI berjalan
sebagai layanan lokal terpisah.

## Pakai dari terminal

Pindah dulu ke folder proyek. Mengetik `freeai` atau `freeai code` membuka
harness coding interaktif. AI membaca dan mencari file, mengusulkan perubahan,
lalu meminta persetujuan sebelum menulis file atau menjalankan perintah.

```sh
cd /path/ke/proyek
freeai
```

Perintah coding yang sama dengan penyedia tertentu:

```sh
freeai code --provider blockrun
```

Sesi tersimpan otomatis di `~/.config/freeai/session.json` (per folder proyek dan
per mode). Lanjutkan dengan `freeai resume` (coding), `freeai code --continue`,
atau `freeai chat --continue`. `/clear` memulai konteks baru dan menimpa sesi
tersimpan; `/quit` mempertahankannya.

Ketik `/model` (atau `/models`) untuk membuka pemilih model. Pakai ↑↓ lalu Enter;
Esc membatalkan. Di terminal tanpa tampilan interaktif, pilih dengan nomor.
Model dipilih dari rute gratis yang siap dan pilihan disimpan untuk sesi berikutnya.
Model individual dari FreeLLMAPI memakai ID asli dari API lokal; daftar dibatasi pada
model gratis yang diekspor oleh FreeAI. Model yang memerlukan key belum ditampilkan
sebagai pilihan siap sebelum key-nya tersedia.

Ketik `/help` untuk daftar perintah, `/` atau `/menu` untuk membuka menu perintah
interaktif (gum, dengan fallback daftar bernomor), `/model list` untuk model siap,
`/model <nomor/nama>` untuk memilih model langsung, `/model auto` untuk pemilihan otomatis,
`/web <kata kunci>` untuk mencari web, `/search auto|always|off` untuk mengatur
pencarian otomatis, `/usage` untuk pemakaian token dan batas penyedia, `/compose` untuk menulis
pesan multi-baris, `/status` untuk status sesi, `/clear` untuk memulai konteks baru,
`/copy` untuk menyalin jawaban terakhir, dan `/quit` untuk keluar.
Tab melengkapi perintah dan nama model; ↑↓ mengakses riwayat input selama sesi.
Riwayat input juga disimpan di `~/.config/freeai/history.txt` (maksimal 500 baris)
dan dimuat lagi pada sesi berikutnya.
Di editor `/compose`, Enter mengirim dan Ctrl+J menambah baris. Ctrl+C membatalkan
input atau proses AI dan kembali ke prompt. Ctrl+D di prompt keluar.
Web search tersedia di mode coding, chat, dan `ask`. Dalam mode `auto` (default),
permintaan pencarian dan pertanyaan terkini memicu tool pencarian sebelum jawaban.
Model juga diminta mencari jika pengetahuannya belum cukup; jika model malah
mengaku tidak dapat mengakses web atau menyatakan keraguan, harness mencoba pencarian
dan meminta jawaban ulang dengan sumber. Ini memakai aturan bahasa dan keputusan model,
bukan pengukuran kepastian yang sempurna. `/search always` memulai setiap permintaan
dengan pencarian, `/search off` memakai pencarian manual.

Pencarian mencoba DuckDuckGo Lite, Bing RSS, lalu DuckDuckGo HTML, menyaring hasil
yang tidak relevan, dan memakai cache selama lima menit. Verifikasi/CAPTCHA atau
HTTP 429 diteruskan sebagai kegagalan mesin tersebut dan dicoba lewat cadangan.
Tool `read_web` membaca halaman sumber serta bagian URL setelah `#`; cuplikan hasil
pencarian tidak dianggap sebagai isi halaman penuh. Jika semua mesin gagal,
FreeAI menampilkan keterbatasannya. Pencarian langsung juga tersedia tanpa memakai model:

```sh
freeai search "Python pathlib documentation"
freeai usage
```

Harness
membatasi akses file ke folder proyek saat ini, mengabaikan folder build/cache
umum, mengecualikan nama file kredensial umum, meminta persetujuan untuk tiap
perubahan dan perintah, lalu menyensor pola key yang umum dalam keluaran perintah.
Ia dapat mencari web tanpa API key dan memakai function calling
dari model gratis yang lulus pemeriksaan tools.
Perintah dijalankan sebagai argumen langsung tanpa shell; command chain dan pipe
tidak diteruskan otomatis. Pemeriksaan yang disarankan AI juga tetap meminta
persetujuan.

CLI chat biasa tersedia dengan `freeai chat`; `freeai ask "pertanyaan"` memberi
satu jawaban. Chat memiliki tool pencarian dan pembacaan sumber web. FreeAI mencoba FreeLLMAPI
lokal terlebih dahulu, lalu memakai rute gratis yang lulus probe sebagai fallback.
Setelah temuan/provider diubah, jalankan:

```sh
freeai refresh --web --tools
freeai list
```

`refresh` menjalankan pencarian/crawl, tes kecil, lalu ekspor konfigurasi.
Tidak ada proses latar atau jadwal otomatis. Jalankan lagi untuk memperbarui.
Percakapan chat dan coding tersimpan otomatis untuk `resume`/`--continue`
(lihat bagian atas); tanpa itu, konteks hanya hidup selama sesi berjalan.
Terminal memakai aksen rainbow pada logo dan garis panel, status model dan auto web di dekat input,
indikator proses, dan tampilan Markdown melalui `gum` bila tersedia. `gum` juga dipakai
untuk pemilih model, pemilih perintah, editor pesan panjang, dan dialog persetujuan.
Di terminal interaktif, jawaban ditampilkan secara streaming token demi token (SSE)
seperti TUI Codex: paragraf dan blok kode dirender inkremental dengan `gum`
(syntax highlighting) sambil menunggu sisanya, disertai spinner menunggu token
pertama. Penyedia yang menolak streaming otomatis jatuh kembali ke jawaban
biasa yang dirender dengan `gum`. Set `FREEAI_STREAM=0` untuk mematikan streaming.
Tanpa `gum`, perintah utama tetap berjalan dalam mode
teks biasa. Set `FREEAI_PLAIN=1` untuk memaksa mode biasa.

`/usage` menampilkan respons dan token sesi ini, pencarian/halaman yang dibaca, serta
catatan bulanan FreeLLMAPI bila layanan lokal tersedia. Hitungan router mencakup
seluruh kliennya dan tidak mencakup request langsung di luar router. Angka tersebut
adalah pemakaian, bukan sisa kuota penyedia. Satu pesan bisa memerlukan beberapa
panggilan model untuk pencarian, pembacaan sumber, atau pekerjaan file.
Menurut [dokumentasi BlockRun](https://blockrun.ai/docs/api-reference/rate-limits)
yang diperiksa 26 Oktober 2026, model gratis dibatasi 30 request per menit dan
300 per jam per IP. Mengganti model pada penyedia yang sama tidak menambah kuota IP.

Jika shortcut belum tersedia:

```sh
python3 /Users/ilyas/Projects/free-ai-collector/freeai.py --help
```

## Yang dicari dan yang diuji

- Pencarian repositori GitHub publik (5 hasil), crawl README dan halaman penyedia.
- Katalog komunitas `mnfst/awesome-free-llm-apis/data.json` untuk menemukan penyedia.
- `--web` menambah pencarian web Bing RSS. Bila dibatasi mesin pencari, kegagalan
  tercatat dan sumber lain tetap dipakai. Bukan crawling seluruh internet.
- Katalog model OpenRouter dibaca langsung. Hanya ID `:free` dengan seluruh
  komponen harga yang dipublikasikan bernilai nol yang lolos penyaringan.
- Katalog BlockRun dibaca langsung. Hanya model yang ditandai tersedia, dengan
  `billing_mode: free` dan seluruh komponen harga nol yang ditambahkan otomatis.
- Seed BlockRun GPT-OSS 20B tanpa key, serta Groq GPT-OSS 20B/120B untuk akun gratis.

Hasil baru dari web/GitHub disimpan sebagai `needs_review`. Crawler tidak bisa
membuktikan syarat gratis hanya dari nama repo. Endpoint yang sudah diketahui
cara akses dan syaratnya masuk katalog uji melalui `providers.json` atau `add`.
Tidak mengambil API key dari halaman atau repositori, tidak membuat akun otomatis,
dan tidak memasang/menjalankan kode yang ditemukan.

Data hasil berada di `data/`:

| File | Isi |
| --- | --- |
| `discovery.json` | Kandidat penyedia, sumber, tautan hasil crawl, dan kegagalan pencarian |
| `catalog.json` | Rute model, bukti/syarat gratis, waktu tes, hasil dan model yang dilaporkan server |
| `freellmapi.config.json` | Endpoint tanpa key yang lulus tes, untuk impor FreeLLMAPI |

`working` berarti endpoint mengikuti tantangan acak dalam tes chat. Ini tidak
membuktikan identitas model di balik server; `served_model` adalah laporan server.
Keberhasilan kedaluwarsa setelah 24 jam untuk CLI dan ekspor baru.
`--tools` menguji keluaran pemanggilan fungsi sederhana; tidak menjalankan kode.
Pengujian ini belum membuktikan kecakapan coding atau seluruh protokol agent.

## Akun gratis dengan API key

Gunakan key khusus akun pada paket gratis. Hanya variabel berikut dibaca, bukan
key milik aplikasi lain di Mac:

- `FREEAI_GROQ_API_KEY`
- `FREEAI_OPENROUTER_API_KEY`

Set key di shell, kemudian jalankan:

```sh
freeai probe --provider groq --limit 2 --tools
freeai ask "Halo" --provider groq
```

Key dibaca saat permintaan dan tidak disimpan dalam data/ekspor. Paket akun harus
diatur gratis di sisi penyedia: endpoint Groq yang sama juga dipakai akun berbayar.
CLI tidak menambah saldo atau mengaktifkan tagihan. OpenRouter hanya memakai model
gratis yang ditemukan dalam katalog saat discovery terakhir; tidak pindah ke ID berbayar.
Probe default maksimal 5 panggilan chat, ditambah 1 panggilan/model bila `--tools`.
Model yang butuh key dilewati tanpa panggilan jaringan. `ask`/`chat` mencoba rute lain
yang baru lulus tes bila permintaan gagal, dan menurunkan status rute gagal.

## Tambah temuan yang sudah diperiksa

Contoh bentuk perintah (alamat/model contoh harus diganti):

```sh
freeai add --name penyedia-baru \
  --base-url https://api.example.com/v1 \
  --model model-gratis \
  --source https://example.com/docs/free \
  --evidence "Dokumentasi menyediakan model ini gratis tanpa akun"
```

Tambahkan `--key-env FREEAI_NAMA_API_KEY` bila perlu key. Perintah menyimpan definisi
di `providers.local.json`; key aslinya tetap di environment. Endpoint baru harus
kompatibel dengan OpenAI Chat Completions. Web chat tanpa API dan protokol khusus
seperti AI Horde dicatat sebagai temuan; adapter-nya belum dibuat.
Jalankan `discover` lalu `probe --provider penyedia-baru` setelah menambahkan.

## Impor ke FreeLLMAPI

Hubungkan CLI ke FreeLLMAPI lokal yang sudah berjalan pada `127.0.0.1:3001`:

```sh
freeai connect
```

Unified API key disimpan di `~/.config/freeai/credentials.json` dengan izin file
privat. CLI mengirim request OpenAI-compatible ke model `auto`, sehingga FreeLLMAPI
memakai fallback chain yang aktif pada dashboard. Pemakaian `auto` dan tool calling
didukung oleh [referensi REST FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/api/01-rest-api.md).

```sh
freeai export
```

Pada instalasi FreeLLMAPI, set variabel berikut **sebelum server dimulai**:

```sh
FREEAPI_CONFIG_PATH=/Users/ilyas/Projects/free-ai-collector/data/freellmapi.config.json
```

Variabel tersebut harus tersedia pada proses server, lalu server dimulai ulang
untuk menerapkan perubahan. Jika menggunakan Docker, mount file tersebut read-only
ke container dan gunakan path di dalam container. Ekspor bukan hot reload dan tidak
memasang FreeLLMAPI. File ini hanya memuat endpoint tanpa key. Untuk akun yang
memerlukan key, tambahkan key melalui dashboard FreeLLMAPI.

Ekspor memakai label `FreeAI / ...` dan `apiKey: no-key` sesuai kontrak startup
FreeLLMAPI. Probe memakai placeholder yang sama. `supportsTools` hanya `true`
bila tes tools lulus. Hasil tes biasa tidak dianggap otomatis mendukung tools.
Ekspor ke file yang sama menyertakan penonaktifan model yang pernah diekspor dan
kini gagal/kedaluwarsa. FreeLLMAPI baru menerapkannya setelah membaca konfigurasi
lagi; konfigurasi yang sudah dimuat tidak otomatis kedaluwarsa setelah 24 jam.

Skema dicek terhadap kode upstream `server/src/services/declarative-config.ts`.
Pengujian lokal ekspor belum sama dengan pengujian impor pada server FreeLLMAPI.

## Pengujian

```sh
cd /Users/ilyas/Projects/free-ai-collector
python3 -m unittest discover -s tests -v
```

Tes offline mencakup penolakan model berbayar, tantangan respons, redirect
kredensial, pembatasan panggilan probe, kedaluwarsa hasil, fallback, ekspor tanpa
key rahasia, dan penonaktifan rute lama. `refresh --tools` menguji jaringan nyata.
