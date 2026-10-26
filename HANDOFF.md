# HANDOFF — FreeAI CLI

Catatan kelanjutan antar agent (Codex → DeepSeek → selanjutnya).
Terakhir diperbarui: 26 Oktober 2026.

## Versi saat ini

**v0.6.0** — render Markdown inkremental saat streaming, spinner menunggu token
pertama, dan sesi tersimpan (`resume`/`--continue`).

## Sudah selesai (Codex, sampai v0.4.0)

- Pencari endpoint AI gratis: pencarian repo GitHub, katalog komunitas
  `mnfst/awesome-free-llm-apis`, katalog OpenRouter/BlockRun `:free`/`billing_mode:free`,
  pencarian web Bing RSS; hasil disimpan di `data/discovery.json` dan `data/catalog.json`.
- Probe endpoint (tantangan acak + tes tools), ekspor konfigurasi FreeLLMAPI,
  perintah `freeai connect` ke FreeLLMAPI lokal (`127.0.0.1:3001/v1`).
- Harness coding interaktif: `list_files`, `read_file`, `search_text`,
  `replace_text`, `create_file`, `run_command` — semua perubahan/perintah
  meminta persetujuan pemilik; file kredensial diblokir; akses dibatasi ke folder proyek.
- Web search tanpa API key: DuckDuckGo Lite → Bing RSS → DuckDuckGo HTML,
  `read_web` pembaca halaman, auto-search `/search auto|always|off` (default auto),
  pemulihan saat model mengaku tidak bisa browsing.
- Visual rainbow (logo/panel/garis), status model + auto web di dekat input,
  render Markdown via `gum`, pemilih model via `gum choose`, `/usage`, `/compose`, `/copy`.
- Keamanan: `public_url` hanya HTTPS publik tanpa kredensial, redirect tidak
  meneruskan kredensial, kredensial disimpan privat (`~/.config/freeai`, mode 0700),
  key tidak pernah masuk `data/` atau ekspor.

## Selesai oleh DeepSeek (v0.5.0–v0.6.0, 26 Okt 2026)

- **Streaming SSE** token-demi-token ala TUI Codex (`stream_complete`):
  parsing `data:` incremental, perakitan `tool_calls` lintas chunk, dekoder UTF-8
  inkremental, penyaring ANSI di `StreamPrinter`, fallback otomatis ke
  `complete()` bila penyedia menolak streaming, dan fallback JSON bila server
  mengabaikan `stream: true`. Matikan dengan `FREEAI_STREAM=0`.
- **Menu perintah** `/` atau `/menu` (`command_menu`): `gum choose` interaktif,
  fallback daftar bernomor tanpa gum.
- **Riwayat input persisten** `~/.config/freeai/history.txt` (maksimal 500 baris),
  dimuat/disimpan otomatis lewat readline.
- **Render Markdown inkremental** saat streaming (`markdown_next` + `StreamPrinter`):
  paragraf dan blok kode fenced dirender per unit dengan `gum format` (syntax
  highlighting) tanpa menunggu jawaban selesai; blok kode ditahan sampai fence
  tertutup agar tidak dirender setengah.
- **Spinner menunggu token pertama** di stderr selama koneksi SSE belum
  menghasilkan delta (`begin_wait`/`stop_wait`).
- **Sesi tersimpan** `~/.config/freeai/session.json` (per folder + per mode):
  `freeai resume`, `freeai code --continue`, `freeai chat --continue`;
  `/clear` menimpa sesi, `/quit` mempertahankannya.
- `/web` tanpa kata kunci sekarang menanyakan kata kunci bila terminal interaktif.
- **Codex asli dengan model FreeAI** (`codex_bridge.py`): jembatan Responses→Chat
  di 127.0.0.1:3002 karena Codex 0.164+ sudah menghapus `wire_api = "chat"`.
  Profil `~/.codex/freeai.config.toml` (wire_api responses, context window 131072),
  wrapper `~/.local/bin/codex-freeai` → symlink ke `codex-freeai` di repo.
  `codex-freeai` menyalakan bridge otomatis, lalu `codex -p freeai`.
  Diverifikasi end-to-end: `codex-freeai exec` menjawab dengan streaming + hooks.
- 52 tes offline lulus (`python3 -m unittest discover -s tests -v`);
  smoke test streaming nyata sukses lewat FreeLLMAPI lokal (freellmapi/auto),
  resume diverifikasi end-to-end lewat pseudo-TTY.

## Cara melanjutkan

```sh
cd ~/Projects/free-ai-collector
python3 -m unittest discover -s tests -v   # wajib hijau sebelum lanjut
freeai                                       # CLI buatan sendiri (v0.6.0)
codex-freeai                                 # Codex asli + model FreeAI
```

- Backlog "parity Codex" yang belum dikerjakan ada di issue GitHub
  (repo `ilyasaalmadani/freeai`). Lihat issue #2 ke atas.
- Kandidat berikutnya: tema terminal (gelap/terang), `/undo` rollback perubahan
  file, keybinding ala Codex, dukungan AI Horde/adaptor protokol non-OpenAI,
  pengukur sisa kuota per penyedia, render diff bertema terang.
- Batas yang tidak bisa ditutup oleh UI: kecerdasan model gratisan jauh di bawah
  GPT-6/Claude Opus yang dipakai Codex/Claude Code — jangan berjanji parity penuh.
- Aturan yang tidak boleh dilanggar: jangan simpan key di `data/`/ekspor,
  jangan akses URL non-publik/non-HTTPS dari crawler, perubahan file dan
  perintah terminal di harness wajib persetujuan pemilik.
