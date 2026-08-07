"""Spiegelt die Urteilssammlung ins Outline-Wiki (wiki.v14.berlin).

Struktur: Unter der Seite "Urteilssammlung" (PARENT_DOC_ID) liegt pro Urteil
eine eigene Unterseite ("Gericht, AZ - Titel" mit Metazeile, Quelle, Leitsätzen).
Die Seite "Urteilssammlung" selbst wird zum Inhaltsverzeichnis (Linkliste,
zuletzt hinzugefügte zuerst).

Die Zuordnung Zotero-Key -> Outline-Dokument steht in wiki_map.json, damit
vorhandene Seiten aktualisiert (statt dupliziert) und entfernte Urteile auch
im Wiki gelöscht werden.

Aufruf durch deploy.sh. Token aus OUTLINE_TOKEN (via .secrets.env). Fehler hier
brechen den Deploy nicht ab (cases.vc ist davon unabhängig).
"""
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

MAX_TITLE = 100  # Outline begrenzt Seitentitel auf 100 Zeichen

DATA = Path(__file__).parent / "data.js"
MAP_FILE = Path(__file__).parent / "wiki_map.json"
API = "https://wiki.v14.berlin/api"
PARENT_DOC_ID = "b8cb8212-826d-46f4-baca-d8bfbbb74337"   # Seite "Urteilssammlung"
COLLECTION_ID = "b7c4555a-cdd7-4e54-ad88-44d997fad26b"
TOKEN = os.environ.get("OUTLINE_TOKEN", "").strip()


def load_items():
    txt = DATA.read_text(encoding="utf-8")
    return json.loads(txt[txt.index("["):txt.rindex("]") + 1])


def load_map():
    if MAP_FILE.exists():
        try:
            return json.loads(MAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_map(m):
    MAP_FILE.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def api(endpoint, payload, tries=6):
    """POST an die Outline-API; drosselt und wiederholt bei 429 (Rate-Limit)."""
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(tries):
        req = urllib.request.Request(
            f"{API}/{endpoint}", data=body, method="POST",
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            time.sleep(0.4)  # sanfte Drosselung zwischen Aufrufen
            return result
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                ra = e.headers.get("Retry-After", "")
                wait = float(ra) if ra.replace(".", "", 1).isdigit() else 2 ** attempt
                time.sleep(min(wait, 30))
                continue
            raise


def cap_title(label):
    return label if len(label) <= MAX_TITLE else label[:MAX_TITLE - 2].rstrip() + "…"


def fmt_date(s):
    s = (s or "")[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        y, m, d = s.split("-")
        return f"{d}.{m}.{y}"
    return s


def title_label(u):
    """'Gericht, AZ - Titel' (eckige Klammern entschärft für Markdown-Links)."""
    left = ", ".join(p for p in [(u.get("court") or "").strip(),
                                 (u.get("docketNumber") or "").strip()] if p)
    title = (u.get("caseName") or "").strip()
    label = f"{left} - {title}" if left and title else (left or title or "Ohne Bezeichnung")
    return label.replace("[", "(").replace("]", ")")


def format_leitsaetze(text):
    lines = [l.strip() for l in (text or "").split("\n") if l.strip()]
    return "\n\n".join(lines)


def child_text(u):
    meta = " · ".join(p for p in [
        (u.get("court") or "").strip(),
        ("Az. " + u["docketNumber"].strip()) if (u.get("docketNumber") or "").strip() else "",
        fmt_date(u.get("dateDecided")),
    ] if p)
    parts = []
    full = title_label(u)
    if len(full) > MAX_TITLE:
        # Bei gekapptem Seitentitel den vollständigen Titel im Text erhalten
        parts.append(f"**{full}**")
    if meta:
        parts.append(f"*{meta}*")
    url = (u.get("url") or "").strip()
    if url:
        parts.append(f"[Volltext / Quelle]({url})")
    tags = [t.strip() for t in (u.get("tags") or []) if t.strip()]
    if tags:
        parts.append("**Schlagworte:** " + ", ".join(tags))
    ls = format_leitsaetze(u.get("leitsaetze"))
    if ls:
        parts.append("## Leitsätze\n\n" + ls)
    return "\n\n".join(parts) + "\n"


def doc_url(d):
    return d.get("url") or ("/doc/" + d.get("urlId", ""))


def upsert(u, mapping):
    """Unterseite anlegen oder aktualisieren; gibt {id, url} zurück."""
    key = u["key"]
    title = cap_title(title_label(u))
    text = child_text(u)
    existing = mapping.get(key)
    if existing and existing.get("id"):
        try:
            d = api("documents.update", {"id": existing["id"], "title": title, "text": text})["data"]
            return {"id": d["id"], "url": doc_url(d)}
        except urllib.error.HTTPError as e:
            if e.code not in (400, 403, 404):
                raise
            # Dokument existiert nicht mehr -> neu anlegen
    d = api("documents.create", {
        "title": title, "text": text,
        "collectionId": COLLECTION_ID, "parentDocumentId": PARENT_DOC_ID,
        "publish": True,
    })["data"]
    return {"id": d["id"], "url": doc_url(d)}


def index_text(entries):
    entries = sorted(entries, key=lambda e: (e["dateAdded"], e["dateDecided"]), reverse=True)
    lines = [
        "Alle Entscheidungen dieser Sammlung – zuletzt hinzugefügte zuerst. "
        "Details jeweils auf der Unterseite.",
        "",
    ]
    lines += [f"- [{e['label']}]({e['url']})" for e in entries]
    return "\n".join(lines) + "\n"


def main():
    if not TOKEN:
        print("OUTLINE_TOKEN fehlt - Wiki-Update uebersprungen.")
        return
    items = load_items()
    mapping = load_map()
    entries = []
    seen = set()
    try:
        for u in items:
            key = u["key"]
            seen.add(key)
            try:
                info = upsert(u, mapping)
            except Exception as e:
                print(f"  Fehler bei {title_label(u)}: {e}")
                continue
            mapping[key] = info
            entries.append({
                "label": title_label(u),
                "url": info["url"],
                "dateAdded": (u.get("dateAdded") or ""),
                "dateDecided": (u.get("dateDecided") or ""),
            })

        # Im Wiki verwaiste Seiten (Urteil in Zotero gelöscht) entfernen
        removed = [k for k in list(mapping) if k not in seen]
        for k in removed:
            try:
                api("documents.delete", {"id": mapping[k]["id"]})
            except Exception:
                pass
            del mapping[k]

        # Übersichtsseite als Inhaltsverzeichnis aktualisieren
        api("documents.update", {"id": PARENT_DOC_ID, "text": index_text(entries)})
        print(f"Wiki: {len(entries)} Unterseiten aktualisiert, {len(removed)} entfernt.")
    finally:
        # Zuordnung immer speichern (auch bei Teilabbruch -> keine Dubletten)
        save_map(mapping)


if __name__ == "__main__":
    main()
