"""Fix all Leitsaetze and case titles in Zotero DB. Reads data from fix_data.json."""
import sqlite3
import sys
import json
import random
import string
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ZOTERO_DB = Path.home() / "Zotero" / "zotero.sqlite"
FIX_DATA = Path(__file__).parent / "fix_data.json"


def build_note_html(paragraphs):
    parts = "".join(f"<p>{p}</p>" for p in paragraphs if p.strip())
    if not parts:
        return None
    return f'<div class="zotero-note znv1"><h2>Leitsätze</h2>{parts}</div>'


def get_next_item_id(cursor):
    cursor.execute("SELECT MAX(itemID) FROM items")
    return cursor.fetchone()[0] + 1


def create_note(conn, parent_item_id, note_html, title="Leitsätze"):
    c = conn.cursor()
    c.execute("SELECT itemTypeID FROM itemTypes WHERE typeName = 'note'")
    note_type_id = c.fetchone()[0]
    c.execute("SELECT libraryID FROM items WHERE itemID = ?", (parent_item_id,))
    library_id = c.fetchone()[0]
    while True:
        key = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        c.execute("SELECT COUNT(*) FROM items WHERE key = ?", (key,))
        if c.fetchone()[0] == 0:
            break
    next_id = get_next_item_id(c)
    c.execute(
        """INSERT INTO items (itemID, itemTypeID, libraryID, key, version, synced,
        dateAdded, dateModified, clientDateModified)
        VALUES (?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'), datetime('now'))""",
        (next_id, note_type_id, library_id, key),
    )
    c.execute(
        "INSERT INTO itemNotes (itemID, parentItemID, note, title) VALUES (?, ?, ?, ?)",
        (next_id, parent_item_id, note_html, title),
    )
    return next_id


def update_case_name(conn, item_id, new_name):
    c = conn.cursor()
    c.execute("SELECT fieldID FROM fields WHERE fieldName = 'caseName'")
    field_id = c.fetchone()[0]
    c.execute("SELECT valueID FROM itemData WHERE itemID = ? AND fieldID = ?",
              (item_id, field_id))
    row = c.fetchone()
    if not row:
        return
    c.execute("SELECT valueID FROM itemDataValues WHERE value = ?", (new_name,))
    val_row = c.fetchone()
    if val_row:
        new_value_id = val_row[0]
    else:
        c.execute("INSERT INTO itemDataValues (value) VALUES (?)", (new_name,))
        new_value_id = c.lastrowid
    c.execute("UPDATE itemData SET valueID = ? WHERE itemID = ? AND fieldID = ?",
              (new_value_id, item_id, field_id))


def main():
    with open(FIX_DATA, "r", encoding="utf-8") as f:
        data = json.load(f)

    titles = data["titles"]
    leitsaetze = data.get("leitsaetze", {})
    to_delete = data.get("leitsaetze_delete", [])
    to_skip = data.get("leitsaetze_skip", [])

    conn = sqlite3.connect(ZOTERO_DB)
    c = conn.cursor()

    c.execute("SELECT fieldID, fieldName FROM fields")
    field_map = dict(c.fetchall())

    # Update titles
    print("=== UPDATING TITLES ===")
    for iid_str, title in titles.items():
        iid = int(iid_str)
        c.execute("""SELECT fieldID, value FROM itemDataValues
            JOIN itemData ON itemData.valueID = itemDataValues.valueID
            WHERE itemData.itemID = ?""", (iid,))
        fields = {field_map.get(r[0]): r[1] for r in c.fetchall()}
        old_name = fields.get("caseName", "")
        if old_name != title:
            update_case_name(conn, iid, title)
            print(f"  {iid}: -> {title}")
        else:
            print(f"  {iid}: OK")

    # Update Leitsaetze
    print("\n=== UPDATING LEITSAETZE ===")
    for iid_str, ls_list in leitsaetze.items():
        iid = int(iid_str)
        title = titles.get(iid_str, f"Item {iid}")

        c.execute("SELECT itemID FROM itemNotes WHERE parentItemID = ? AND title = 'Leitsätze'",
                  (iid,))
        existing = c.fetchone()

        note_html = build_note_html(ls_list)
        if existing:
            c.execute("UPDATE itemNotes SET note = ? WHERE itemID = ?",
                      (note_html, existing[0]))
            print(f"  UPDATED: {title}")
        else:
            nid = create_note(conn, iid, note_html)
            print(f"  CREATED {nid}: {title}")

    # Delete notes that are all redaktionell
    for iid_str in to_delete:
        iid = int(iid_str)
        title = titles.get(iid_str, f"Item {iid}")
        c.execute("SELECT itemID FROM itemNotes WHERE parentItemID = ? AND title = 'Leitsätze'",
                  (iid,))
        existing = c.fetchone()
        if existing:
            c.execute("DELETE FROM itemNotes WHERE itemID = ?", (existing[0],))
            c.execute("DELETE FROM items WHERE itemID = ?", (existing[0],))
            print(f"  DELETED: {title}")

    # Report skipped
    for iid_str in to_skip:
        title = titles.get(iid_str, f"Item {iid_str}")
        print(f"  SKIP: {title} (needs manual check or not found)")

    conn.commit()
    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
