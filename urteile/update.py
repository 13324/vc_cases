import sqlite3
import json
import re
from pathlib import Path
from html.parser import HTMLParser

ZOTERO_DB = Path.home() / "Zotero" / "zotero.sqlite"
OUTPUT = Path(__file__).parent / "data.js"
COLLECTION_NAME = "Urteile"


class NoteTextExtractor(HTMLParser):
    """Extract plain text from a Zotero note HTML, split by h2/h3 sections."""

    def __init__(self):
        super().__init__()
        self.sections = {}
        self.current_heading = None
        self.current_text = []
        self.in_heading = False
        self.heading_text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3"):
            self._flush_section()
            self.in_heading = True
            self.heading_text = []
        if tag == "p" and self.current_text and not self.current_text[-1].endswith("\n"):
            self.current_text.append("\n")
        if tag == "br":
            self.current_text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("h2", "h3") and self.in_heading:
            self.in_heading = False
            self.current_heading = "".join(self.heading_text).strip()
        if tag == "p":
            self.current_text.append("\n")

    def handle_data(self, data):
        if self.in_heading:
            self.heading_text.append(data)
        else:
            self.current_text.append(data)

    def _flush_section(self):
        text = "".join(self.current_text).strip()
        if text and self.current_heading:
            self.sections[self.current_heading] = text
        self.current_text = []

    def get_sections(self):
        self._flush_section()
        return self.sections


def extract_note_sections(note_html):
    """Parse a Zotero note and return dict of heading -> text."""
    p = NoteTextExtractor()
    p.feed(note_html)
    return p.get_sections()


def note_to_plain_text(note_html):
    """Convert note HTML to plain text, skipping headings."""
    class SimpleExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text = []
            self.in_heading = False
        def handle_starttag(self, tag, attrs):
            if tag in ("h2", "h3"):
                self.in_heading = True
            if tag in ("p", "br", "div"):
                self.text.append("\n")
        def handle_endtag(self, tag):
            if tag in ("h2", "h3"):
                self.in_heading = False
        def handle_data(self, data):
            if not self.in_heading:
                self.text.append(data)

    p = SimpleExtractor()
    p.feed(note_html)
    return re.sub(r"\n{3,}", "\n\n", "".join(p.text)).strip()


conn = sqlite3.connect(ZOTERO_DB)
c = conn.cursor()

c.execute("SELECT collectionID FROM collections WHERE collectionName = ?", (COLLECTION_NAME,))
row = c.fetchone()
if not row:
    print(f"Collection '{COLLECTION_NAME}' not found.")
    exit(1)

col_id = row[0]

c.execute("""
    SELECT ci.itemID FROM collectionItems ci
    JOIN items i ON ci.itemID = i.itemID
    WHERE ci.collectionID = ? AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
""", (col_id,))
item_ids = [r[0] for r in c.fetchall()]

c.execute("SELECT fieldID, fieldName FROM fields")
field_map = dict(c.fetchall())

c.execute("SELECT predicateID FROM relationPredicates WHERE predicate = ?", ("dc:relation",))
row = c.fetchone()
dc_relation_id = row[0] if row else None

items = []
for iid in item_ids:
    c.execute("SELECT key FROM items WHERE itemID = ?", (iid,))
    item_key = c.fetchone()[0]

    c.execute("""
        SELECT fieldID, value FROM itemDataValues
        JOIN itemData ON itemData.valueID = itemDataValues.valueID
        WHERE itemData.itemID = ?
    """, (iid,))
    fields = {field_map.get(r[0]): r[1] for r in c.fetchall()}

    c.execute("""
        SELECT t.name FROM tags t
        JOIN itemTags it ON it.tagID = t.tagID
        WHERE it.itemID = ?
        ORDER BY t.name
    """, (iid,))
    all_tags = [r[0] for r in c.fetchall()]
    highlight = "Highlight" in all_tags
    tags = [t for t in all_tags if t != "Highlight"]

    # Get related item keys
    related = []
    if dc_relation_id is not None:
        c.execute("""
            SELECT object FROM itemRelations
            WHERE itemID = ? AND predicateID = ?
        """, (iid, dc_relation_id))
        for (uri,) in c.fetchall():
            related.append(uri.rsplit("/", 1)[-1])

    # Get notes
    c.execute("SELECT title, note FROM itemNotes WHERE parentItemID = ?", (iid,))
    notes_raw = c.fetchall()

    leitsaetze = ""
    kommentar = ""
    for title, note_html in notes_raw:
        if title == "Leitsätze":
            leitsaetze = note_to_plain_text(note_html)
        elif title == "Kommentar":
            kommentar = note_to_plain_text(note_html)
        elif not title or title not in ("Additional Metadata",):
            # Check if the note has structured sections
            sections = extract_note_sections(note_html)
            if "Leitsätze" in sections and not leitsaetze:
                leitsaetze = sections["Leitsätze"]
            if "Kommentar" in sections and not kommentar:
                kommentar = sections["Kommentar"]

    items.append({
        "key": item_key,
        "caseName": fields.get("caseName", ""),
        "court": fields.get("court", ""),
        "dateDecided": (fields.get("dateDecided", ""))[:10],
        "docketNumber": fields.get("docketNumber", ""),
        "url": fields.get("url", ""),
        "tags": tags,
        "highlight": highlight,
        "related": related,
        "leitsaetze": leitsaetze,
        "kommentar": kommentar,
    })

conn.close()

OUTPUT.write_text(
    "const urteile = " + json.dumps(items, indent=2, ensure_ascii=False) + ";\n",
    encoding="utf-8",
)
print(f"Exported {len(items)} entries to {OUTPUT}")
