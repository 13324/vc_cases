"""Erzeugt eine Commit-Nachricht, die auflistet, welche Urteile hinzugekommen
oder entfernt wurden. Vergleicht die aktuelle data.js (auf der Platte) mit der
zuletzt committeten Version (git show HEAD:urteile/data.js).

Aufruf aus dem Repo-Root (macht deploy.sh). Gibt die Nachricht auf stdout aus.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # collection/
NEW = REPO / "urteile" / "data.js"


def parse(txt):
    """data.js ist 'const urteile = [ ... ];' -> Array-Teil als JSON laden."""
    start = txt.index("[")
    end = txt.rindex("]")
    return json.loads(txt[start:end + 1])


def load_new():
    return parse(NEW.read_text(encoding="utf-8"))


def load_old():
    try:
        res = subprocess.run(
            ["git", "show", "HEAD:urteile/data.js"],
            cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        )
        if res.returncode != 0 or not res.stdout.strip():
            return []
        return parse(res.stdout)
    except Exception:
        return []


def ident(c):
    """Gericht + Aktenzeichen als Kurzbezeichnung."""
    parts = [c.get("court", "").strip(), c.get("docketNumber", "").strip()]
    label = " ".join(p for p in parts if p)
    return label or "(ohne Aktenzeichen)"


def line(c):
    name = c.get("caseName", "").strip()
    return f"{ident(c)} — {name}" if name else ident(c)


def main():
    new = load_new()
    old = load_old()

    old_keys = {c["key"] for c in old}
    new_keys = {c["key"] for c in new}
    added = [c for c in new if c["key"] not in old_keys]
    removed = [c for c in old if c["key"] not in new_keys]

    # Betreffzeile
    if added and not removed:
        subject = (f"Neues Urteil: {ident(added[0])}" if len(added) == 1
                   else f"{len(added)} neue Urteile")
    elif added and removed:
        subject = f"{len(added)} neue, {len(removed)} entfernte Urteile"
    elif removed and not added:
        subject = (f"Urteil entfernt: {ident(removed[0])}" if len(removed) == 1
                   else f"{len(removed)} Urteile entfernt")
    else:
        # Keine Zu-/Abgänge -> nur inhaltliche Änderungen an bestehenden Urteilen
        print("Urteile aktualisiert")
        return

    body = []
    if added:
        body.append("")
        body.append("Neu:")
        body += [f"- {line(c)}" for c in added]
    if removed:
        body.append("")
        body.append("Entfernt:")
        body += [f"- {line(c)}" for c in removed]

    print(subject)
    if body:
        print("\n".join(body))


if __name__ == "__main__":
    main()
