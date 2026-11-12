"""
Ringkasan artikel → 3-5 poin penting berbahasa Indonesia.

- Jika env ANTHROPIC_API_KEY tersedia: diringkas oleh Claude (hasil terbaik, ditulis ulang).
- Jika tidak (atau panggilan gagal): ringkasan ekstraktif — memilih kalimat terpenting
  dari artikel berdasarkan kata kunci judul, angka/spesifikasi, dan frekuensi kata.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter

USE_AI = True
MODEL = "claude-opus-5-5"

# --------------------------------------------------------------------------- #
# Ekstraktif (tanpa API)
# --------------------------------------------------------------------------- #
STOP = set("""yang dan di ke dari untuk pada dengan ini itu juga akan atau karena adalah sebagai dalam
tidak bisa sudah telah oleh para saat lebih masih hanya namun tapi jadi kalau seperti agar bagi
mereka kita kami saya anda bro sob sobat cak cakkk iwb tmcblog pertamax7 nih nah lho loh deh sih ya
the and for with that this from ada punya buat tersebut hingga serta pun nya bukan banget tentu
sangat makin semakin memang yakni yaitu antara sebuah secara dapat harus belum lagi kembali baru""".split())

UNIT = re.compile(r"\d[\d.,]*\s?(cc|hp|ps|kw|nm|rpm|km|kg|mm|inci|inch|liter|l\b|juta|ribu|miliar|unit|persen|%|yen|rm\b|usd|euro)|rp\s?\d", re.I)
LEAD = re.compile(r"^\s*(iwanbanaran\.com|tmcblog\.com|pertamax7\.com)\s*[–—-]\s*", re.I)
FILLER = re.compile(r"^\s*(cak+|sob+|bro+|nah|well|oke|ok|sobat \w+ sekalian)\b[\s.,!…]*", re.I)
OUTRO = re.compile(r"(taufik of buaran|iwb\)?\s*$|baca juga|semoga (berguna|bermanfaat)|silakan komentar)", re.I)


def _sentences(text: str) -> list[str]:
    text = LEAD.sub("", text or "")
    parts = re.split(r"(?<=[.!?…])\s+(?=[A-Z0-9“\"(])", text)
    out = []
    for p in parts:
        p = LEAD.sub("", re.sub(r"\s+", " ", p).strip())
        p = re.sub(r"\s+([!?.,])", r"\1", p).rstrip("!")
        for _ in range(3):
            p = FILLER.sub("", p)
        p = re.sub(r"[.!…]{2,}", ".", p).strip(" .…") + "."
        if 45 <= len(p) <= 320 and not OUTRO.search(p):
            out.append(p[0].upper() + p[1:])
    return out


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9-]+", s.lower()) if len(w) > 2 and w not in STOP]


def extractive_points(title: str, text: str, n: int = 4) -> list[str]:
    sents = _sentences(text)
    if not sents:
        return []
    tf = Counter(w for s in sents for w in _words(s))
    title_w = set(_words(title))
    scored = []
    for i, s in enumerate(sents):
        ws = _words(s)
        if not ws:
            continue
        score = sum(tf[w] for w in ws) / math.sqrt(len(ws)) / max(tf.most_common(1)[0][1], 1)
        score += 0.8 * len(title_w & set(ws))
        score += 0.9 * min(len(UNIT.findall(s)), 3)
        score += 1.2 if i == 0 else 0.5 if i == 1 else 0
        if s.endswith("?.") or "?" in s:
            score -= 1.5
        scored.append((score, i, s, set(ws)))
    picked: list[tuple[int, str, set]] = []
    for score, i, s, ws in sorted(scored, reverse=True):
        if all(len(ws & w2) / max(len(ws | w2), 1) < 0.45 for _, _, w2 in picked):
            picked.append((i, s, ws))
        if len(picked) >= n:
            break
    return [s for _, s, _ in sorted(picked)]


# --------------------------------------------------------------------------- #
# AI (Claude)
# --------------------------------------------------------------------------- #
SYSTEM = """Kamu analis industri sepeda motor di Indonesia. Tugasmu meringkas artikel blog otomotif \
menjadi poin-poin untuk rekap "Motorcycle Issue" yang dibaca tim internal pabrikan motor, supaya \
mereka tidak perlu membaca artikel aslinya.

Aturan:
- Tulis 3 sampai 5 poin dalam bahasa Indonesia yang baku dan lugas. Buang gaya bahasa blog \
(sapaan, candaan, opini berbunga-bunga).
- Setiap poin satu kalimat padat yang bisa berdiri sendiri. Poin pertama menyatakan inti beritanya.
- Pertahankan fakta spesifik: nama model, kode, spesifikasi, angka, harga, tanggal, negara/pasar.
- Jika artikel memuat dampak atau relevansi untuk pasar Indonesia, jadikan itu poin terakhir.
- Hanya gunakan informasi dari artikel. Jangan menambah fakta atau spekulasi sendiri; jika artikel \
berspekulasi, tandai sebagai prediksi/rumor."""

SCHEMA = {
    "type": "object",
    "properties": {"points": {"type": "array", "items": {"type": "string"}}},
    "required": ["points"],
    "additionalProperties": False,
}


def _ai_points(client, title: str, source: str, text: str) -> list[str]:
    import anthropic

    kwargs = dict(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": f"Sumber: {source}\nJudul: {title}\n\nIsi artikel:\n{text}"}],
    )
    try:
        # fallback sisi server: bila model menolak, API mengulang di model cadangan
        resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except anthropic.BadRequestError:
        resp = client.messages.create(**kwargs)
    if resp.stop_reason in ("refusal", "max_tokens"):
        return []
    raw = next((b.text for b in resp.content if b.type == "text"), "")
    points = json.loads(raw).get("points", [])
    return [p.strip() for p in points if isinstance(p, str) and p.strip()][:5]


def summarize_all(articles) -> None:
    """Mengisi .points dan .summary_by pada setiap artikel."""
    client = None
    if USE_AI and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic(max_retries=4)
        except ImportError:
            print("  ! paket 'anthropic' belum terpasang → ringkasan ekstraktif", file=sys.stderr)
    print(f"Meringkas {len(articles)} artikel ({'AI' if client else 'ekstraktif'})")
    ai_ok = ai_fail = 0
    for a in articles:
        text = a.text or a.summary
        if client and len(text) > 200:
            import anthropic
            try:
                a.points = _ai_points(client, a.title, a.source, text)
            except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
                print(f"  ! API key ditolak ({e}); sisa artikel diringkas ekstraktif", file=sys.stderr)
                client = None
            except anthropic.RateLimitError as e:
                print(f"  ! rate limit: {e}", file=sys.stderr)
            except anthropic.APIStatusError as e:
                print(f"  ! API error {e.status_code}: {e.message}", file=sys.stderr)
            except (anthropic.APIConnectionError, json.JSONDecodeError) as e:
                print(f"  ! gagal meringkas {a.url}: {e}", file=sys.stderr)
            if a.points:
                a.summary_by = "ai"
                ai_ok += 1
                continue
            ai_fail += 1
        a.points = extractive_points(a.title, text)
        a.summary_by = "auto"
    if ai_ok or ai_fail:
        print(f"  AI: {ai_ok} berhasil, {ai_fail} jatuh ke ekstraktif")
