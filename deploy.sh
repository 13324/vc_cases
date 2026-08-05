#!/bin/bash
# Deploy der Rechtsprechungssammlung nach Codeberg Pages (https://cases.vc).
#
#   main-Branch  = Quelle + Pipeline (dieses Verzeichnis, inkl. update.py/deploy.sh)
#   pages-Branch = ausgelieferte Seite (nur index.html/app.js/style.css/data.js im Root)
#
# Codeberg liefert den pages-Branch aus. Zugangsdaten stehen in .secrets.env
# (CODEBERG_USER, CODEBERG_TOKEN) und sind per .gitignore vom Repo ausgeschlossen.
set -e
cd "$(dirname "$0")"

if [ ! -f .secrets.env ]; then
    echo "FEHLER: .secrets.env fehlt (CODEBERG_USER, CODEBERG_TOKEN)."
    exit 1
fi
set -a; . ./.secrets.env; set +a

REPO_URL="https://${CODEBERG_USER}:${CODEBERG_TOKEN}@codeberg.org/${CODEBERG_USER}/cases.git"

echo "=== 1/3  Export aus Zotero ==="
PYTHONUTF8=1 python urteile/update.py

echo ""
echo "=== 2/3  Quelle committen und nach main pushen ==="
git add -A
if git diff --cached --quiet; then
    echo "Keine Quell-Aenderungen."
    MSG="Update site"
else
    MSG=$(PYTHONUTF8=1 python urteile/gen_commit_msg.py)
    git commit -m "$MSG"
    git push "$REPO_URL" main
    echo "main gepusht (Codeberg)."
fi

# GitHub-Mirror: main immer nach origin spiegeln (reines Archiv, KEIN GitHub Pages).
if git push origin main 2>/dev/null; then
    echo "main gespiegelt (GitHub)."
else
    echo "Hinweis: GitHub-Mirror-Push fehlgeschlagen (Auth/Netz?) - Codeberg ist maßgeblich."
fi

echo ""
echo "=== 3/3  Seite in den pages-Branch bauen und pushen ==="
TMP=$(mktemp -d)
if git clone --quiet --branch pages "$REPO_URL" "$TMP" 2>/dev/null; then
    :
else
    git clone --quiet "$REPO_URL" "$TMP"
    ( cd "$TMP" && git checkout --quiet --orphan pages && git rm -rfq . 2>/dev/null || true )
fi
cp urteile/index.html urteile/app.js urteile/style.css urteile/data.js "$TMP"/
(
    cd "$TMP"
    # Nur die vier Seiten-Dateien stagen (kein -A: sonst landen z.B. vom
    # Windows-Credential-Manager erzeugte Sentinel-Dateien im pages-Branch).
    git add index.html app.js style.css data.js
    if git diff --cached --quiet; then
        echo "pages unveraendert."
    else
        git commit --quiet -m "$MSG"
        git push --quiet "$REPO_URL" pages
        echo "pages gepusht."
    fi
)
rm -rf "$TMP"

echo ""
echo "Fertig! Codeberg baut die Seite neu - in ~1 Minute live unter https://cases.vc"
