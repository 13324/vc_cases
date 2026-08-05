"""Extract Leitsätze from Zotero snapshots and write them as notes into the Zotero DB."""
import sqlite3
import sys
import os
import re
from html.parser import HTMLParser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ZOTERO_DB = Path.home() / "Zotero" / "zotero.sqlite"
STORAGE = Path.home() / "Zotero" / "storage"
COLLECTION_NAME = "Urteile"


class LeitsatzExtractor(HTMLParser):
    """Extract content from divs with class containing 'leitsatz'."""

    def __init__(self):
        super().__init__()
        self.in_leitsatz = False
        self.div_depth = 0
        self.text = []
        self.sections = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        if not self.in_leitsatz and "leitsatz" in cls:
            self.in_leitsatz = True
            self.div_depth = 1
            self.text = []
            return
        if self.in_leitsatz:
            if tag in ("div", "section", "article"):
                self.div_depth += 1
            if tag == "br":
                self.text.append("\n")
            if tag == "p" and self.text and not self.text[-1].endswith("\n"):
                self.text.append("\n")

    def handle_endtag(self, tag):
        if self.in_leitsatz:
            if tag in ("div", "section", "article"):
                self.div_depth -= 1
            if tag == "p":
                self.text.append("\n")
            if self.div_depth <= 0:
                t = "".join(self.text).strip()
                if t:
                    self.sections.append(t)
                self.in_leitsatz = False
                self.text = []

    def handle_data(self, data):
        if self.in_leitsatz:
            self.text.append(data)


def extract_from_html(filepath):
    """Extract Leitsätze from a beck-online HTML snapshot."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    p = LeitsatzExtractor()
    p.feed(content)
    return p.sections


def clean_leitsatz(text):
    """Clean up extracted Leitsatz text."""
    # Remove redundant section labels that stand alone
    text = re.sub(r"^(Amtliche[r]?\s+)?Leitsätz?e?:?\s*$", "", text, flags=re.MULTILINE).strip()
    text = re.sub(r"^Redaktionelle[r]?\s+Leitsätz?e?:?\s*$", "", text, flags=re.MULTILINE).strip()
    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove law reference artifacts like "§ GMBHG § 40 GMBHG § 40 Absatz II"
    # Keep them as-is since they are part of the legal text
    return text.strip()


def build_note_html(leitsaetze):
    """Build a Zotero note HTML from extracted Leitsätze."""
    parts = []
    for ls in leitsaetze:
        ls = clean_leitsatz(ls)
        if not ls:
            continue
        # Convert newlines to paragraphs
        paragraphs = [p.strip() for p in ls.split("\n") if p.strip()]
        for p in paragraphs:
            parts.append(f"<p>{p}</p>")
    if not parts:
        return None
    html = '<div class="zotero-note znv1"><h2>Leitsätze</h2>' + "".join(parts) + "</div>"
    return html


def get_next_item_id(cursor):
    """Get the next available itemID."""
    cursor.execute("SELECT MAX(itemID) FROM items")
    return cursor.fetchone()[0] + 1


def create_note(conn, parent_item_id, note_html, title="Leitsätze"):
    """Create a new Zotero note attached to a parent item."""
    c = conn.cursor()

    # Get the itemTypeID for 'note'
    c.execute("SELECT itemTypeID FROM itemTypes WHERE typeName = 'note'")
    note_type_id = c.fetchone()[0]

    # Get the libraryID from parent
    c.execute("SELECT libraryID FROM items WHERE itemID = ?", (parent_item_id,))
    library_id = c.fetchone()[0]

    # Generate a unique key (8 char alphanumeric)
    import random
    import string
    while True:
        key = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        c.execute("SELECT COUNT(*) FROM items WHERE key = ?", (key,))
        if c.fetchone()[0] == 0:
            break

    next_id = get_next_item_id(c)

    # Insert into items table
    c.execute(
        """INSERT INTO items (itemID, itemTypeID, libraryID, key, version, synced, dateAdded, dateModified, clientDateModified)
        VALUES (?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'), datetime('now'))""",
        (next_id, note_type_id, library_id, key),
    )

    # Insert into itemNotes
    c.execute(
        "INSERT INTO itemNotes (itemID, parentItemID, note, title) VALUES (?, ?, ?, ?)",
        (next_id, parent_item_id, note_html, title),
    )

    return next_id


def main():
    conn = sqlite3.connect(ZOTERO_DB)
    c = conn.cursor()

    # Get collection
    c.execute("SELECT collectionID FROM collections WHERE collectionName = ?", (COLLECTION_NAME,))
    row = c.fetchone()
    if not row:
        print(f"Collection '{COLLECTION_NAME}' not found.")
        return
    col_id = row[0]

    # Get items
    c.execute(
        """SELECT ci.itemID FROM collectionItems ci
        JOIN items i ON ci.itemID = i.itemID
        WHERE ci.collectionID = ? AND i.itemID NOT IN (SELECT itemID FROM deletedItems)""",
        (col_id,),
    )
    item_ids = [r[0] for r in c.fetchall()]

    c.execute("SELECT fieldID, fieldName FROM fields")
    field_map = dict(c.fetchall())

    created = 0
    skipped_existing = 0
    skipped_no_data = 0

    for iid in item_ids:
        # Get case name
        c.execute(
            """SELECT fieldID, value FROM itemDataValues
            JOIN itemData ON itemData.valueID = itemDataValues.valueID
            WHERE itemData.itemID = ?""",
            (iid,),
        )
        fields = {field_map.get(r[0]): r[1] for r in c.fetchall()}
        case_name = fields.get("caseName", "?")

        # Check if Leitsätze note already exists
        c.execute("SELECT itemID, title FROM itemNotes WHERE parentItemID = ?", (iid,))
        existing = c.fetchall()
        if any(t == "Leitsätze" for _, t in existing):
            print(f"  SKIP (already has Leitsätze note): {case_name[:80]}")
            skipped_existing += 1
            continue

        # Find HTML attachments
        c.execute(
            """SELECT i.key, ia.path FROM itemAttachments ia
            JOIN items i ON ia.itemID = i.itemID
            WHERE ia.parentItemID = ? AND ia.contentType = 'text/html'
            AND i.itemID NOT IN (SELECT itemID FROM deletedItems)""",
            (iid,),
        )
        attachments = c.fetchall()

        leitsaetze = []
        for key, path in attachments:
            if not path:
                continue
            filename = path.replace("storage:", "")
            filepath = STORAGE / key / filename
            if not filepath.exists():
                continue
            extracted = extract_from_html(filepath)
            if extracted:
                leitsaetze = extracted
                break

        if not leitsaetze:
            print(f"  NO LEITSÄTZE: {case_name[:80]}")
            skipped_no_data += 1
            continue

        note_html = build_note_html(leitsaetze)
        if not note_html:
            print(f"  EMPTY after cleaning: {case_name[:80]}")
            skipped_no_data += 1
            continue

        note_id = create_note(conn, iid, note_html)
        print(f"  CREATED note {note_id}: {case_name[:80]}")
        created += 1

    conn.commit()
    conn.close()

    print(f"\nDone: {created} notes created, {skipped_existing} skipped (existing), {skipped_no_data} skipped (no data)")


if __name__ == "__main__":
    main()
