"""Aktualisiert den Outline-Wiki-Eintrag "Urteilssammlung" mit allen Urteilen.

Liest urteile/data.js und schreibt eine formatierte Markdown-Liste in das
Dokument: pro Urteil eine Überschrift "Gericht, AZ - Titel" (verlinkt auf die
Quelle), darunter die Leitsätze, soweit vorhanden.

Wird von deploy.sh aufgerufen. Der API-Token kommt aus der Umgebung
(OUTLINE_TOKEN, gesetzt via .secrets.env) und wird nie ins Repo geschrieben.
Fehler hier lassen den Deploy nicht scheitern (cases.vc ist davon unabhängig).
"""
import json
import os
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data.js"
API = "https://wiki.v14.berlin/api"
DOC_ID = "b8cb8212-826d-46f4-baca-d8bfbbb74337"  # Dokument "Urteilssammlung"
TOKEN = os.environ.get("OUTLINE_TOKEN", "").strip()


def load_items():
    txt = DATA.read_text(encoding="utf-8")
    return json.loads(txt[txt.index("["):txt.rindex("]") + 1])


def heading_label(u):
    """'Gericht, AZ - Titel' (Teile weggelassen, wenn leer)."""
    left = ", ".join(p for p in [(u.get("court") or "").strip(),
                                 (u.get("docketNumber") or "").strip()] if p)
    title = (u.get("caseName") or "").strip()
    label = f"{left} - {title}" if left and title else (left or title or "Ohne Bezeichnung")
    # eckige Klammern würden die Markdown-Linksyntax brechen
    return label.replace("[", "(").replace("]", ")")


def format_leitsaetze(text):
    """Zeilen als eigene Blöcke (nummerierte Leitsätze werden so zur Liste)."""
    lines = [l.strip() for l in (text or "").split("\n") if l.strip()]
    return "\n\n".join(lines)


def build_markdown(items):
    # Zuletzt hinzugefügt zuerst (Tiebreaker: neuestes Entscheidungsdatum)
    items = sorted(items, key=lambda u: (u.get("dateAdded") or "", u.get("dateDecided") or ""), reverse=True)
    blocks = []
    for u in items:
        label = heading_label(u)
        url = (u.get("url") or "").strip()
        heading = f"## [{label}]({url})" if url else f"## {label}"
        ls = format_leitsaetze(u.get("leitsaetze"))
        blocks.append(heading + ("\n\n" + ls if ls else ""))
    return "\n\n".join(blocks) + "\n"


def update_document(text):
    body = json.dumps({"id": DOC_ID, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/documents.update", data=body, method="POST",
        headers={"Authorization": f"Bearer {TOKEN}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    if not TOKEN:
        print("OUTLINE_TOKEN fehlt - Wiki-Update uebersprungen.")
        return
    items = load_items()
    md = build_markdown(items)
    try:
        res = update_document(md)
        if res.get("data"):
            print(f"Wiki aktualisiert: {len(items)} Urteile im Eintrag 'Urteilssammlung'.")
        else:
            print("Wiki-Update-Antwort:", json.dumps(res)[:200])
    except Exception as e:
        print(f"Wiki-Update fehlgeschlagen (Deploy davon unberuehrt): {e}")


if __name__ == "__main__":
    main()
