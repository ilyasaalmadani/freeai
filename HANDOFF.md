# HANDOFF — FreeAI CLI

Catatan kelanjutan antar agent (Codex → DeepSeek → selanjutnya).
Terakhir diperbarui: 26 Oktober 2026.

## Versi saat ini

**v0.5.0** — streaming jawaban token-demi-token (SSE), menu perintah interaktif,
dan riwayat input persisten.

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

## Selesai oleh DeepSeek (v0.5.0, 26 Okt 2026)

- **Streaming SSE** token-demi-token ala TUI Codex (`stream_complete`):
  parsing `data:` incremental, perakitan `tool_calls` lintas chunk, dekoder UTF-8
  inkremental, penyaring ANSI di `StreamPrinter`, fallback otomatis ke
  `complete()` bila penyedia menolak streaming, dan fallback JSON bila server
  mengabaikan `stream: true`. Matikan dengan `FREEAI_STREAM=0`.
- **Menu perintah** `/` atau `/menu` (`command_menu`): `gum choose` interaktif,
  fallback daftar bernomor tanpa gum.
- **Riwayat input persisten** `~/.config/freeai/history.txt` (maksimal 500 baris),
  dimuat/disimpan otomatis lewat readline.
- `/web` tanpa kata kunci sekarang menanyakan kata kunci bila terminal interaktif.
- 41 tes offline lulus (`python3 -m unittest discover -s tests -v`);
  smoke test streaming nyata sukses lewat FreeLLMAPI lokal (freellmapi/auto).

## Cara melanjutkan

```sh
cd ~/Projects/free-ai-collector
python3 -m unittest discover -s tests -v   # wajib hijau sebelum lanjut
freeai                                       # atau ./freeai.py
```

- Backlog "parity Codex" yang belum dikerjakan ada di issue GitHub
  (repo `ilyasaalmadani/freeai`). Lihat issue #2 ke atas.
- Kandidat berikutnya: spinner "menunggu token pertama" saat streaming lambat,
  render markdown inkremental, tema terminal (gelap/terang), sesi/riwayat chat
  tersimpan, `/undo` rollback perubahan file, dukungan AI Horde/adaptor protokol
  non-OpenAI, pengukur sisa kuota per penyedia.
- Aturan yang tidak boleh dilanggar: jangan simpan key di `data/`/ekspor,
  jangan akses URL non-publik/non-HTTPS dari crawler, perubahan file dan
  perintah terminal di harness wajib persetujuan pemilik.
