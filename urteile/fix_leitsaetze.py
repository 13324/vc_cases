"""Clean up existing Leitsätze notes and add missing ones from web research."""
import sqlite3
import sys
import re
import random
import string
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ZOTERO_DB = Path.home() / "Zotero" / "zotero.sqlite"
COLLECTION_NAME = "Urteile"


def clean_gesetzesverweise(text):
    """Fix beck-online style law references to proper citation format."""
    # Pattern: § GMBHG § 40 GMBHG § 40 Absatz II -> § 40 Abs. 2 GmbHG
    # Pattern: § BGB § 652 BGB § 652 Absatz I -> § 652 Abs. 1 BGB
    # Pattern: § INSO § 19 Abs. INSO § 19 Absatz 2 -> § 19 Abs. 2 InsO
    # Pattern: § ZPO § 173 Abs. ZPO § 173 Absatz 2 -> § 173 Abs. 2 ZPO
    # Pattern: § HGB § 272 Abs. HGB § 272 Absatz 2 Nr. HGB § 272 Absatz 2 Nummer 1 HGB
    # Pattern: § AKTG § 182 AktG -> § 182 AktG

    law_name_map = {
        "GMBHG": "GmbHG",
        "BGB": "BGB",
        "INSO": "InsO",
        "ZPO": "ZPO",
        "HGB": "HGB",
        "AKTG": "AktG",
        "FAMFG": "FamFG",
        "WPUEG_ANGV": "WpÜG-AV",
        "EGINSO": "EGInsO",
    }

    roman_to_arabic = {
        "I": "1", "II": "2", "III": "3", "IV": "4",
        "V": "5", "VI": "6", "VII": "7", "VIII": "8",
    }

    def replace_roman(m):
        return roman_to_arabic.get(m.group(0), m.group(0))

    # Handle complex patterns with multiple redundant law name refs
    # e.g. "§ GMBHG § 40 GMBHG § 40 Absatz II GmbHG"
    # Strategy: repeatedly simplify
    for code, proper in law_name_map.items():
        # Remove redundant "CODE § XX CODE § XX" patterns
        # "§ CODE § NN" -> "§ NN"
        text = re.sub(rf"§\s+{code}\s+§\s+", "§ ", text)
        # "Abs. CODE § NN Absatz" -> "Abs."  (remove embedded re-references)
        text = re.sub(rf"\bAbs\.\s+{code}\s+§\s+\d+\s+Absatz", "Abs.", text)
        text = re.sub(rf"\bAbsatz\s+{code}\s+§\s+\d+\s+Absatz", "Abs.", text)
        # "Nr. CODE § NN Absatz NN Nummer" -> "Nr."
        text = re.sub(rf"\bNr\.\s+{code}\s+§\s+\d+\s+Absatz\s+\d+\s+Nummer", "Nr.", text)
        # "S. CODE § NN Absatz" -> "S."
        text = re.sub(rf"\bS\.\s+{code}\s+§\s+\d+\s+", "S. ", text)
        # Replace "CODE" as standalone with proper name
        text = re.sub(rf"\b{code}\b", proper, text)

    # "Absatz" -> "Abs."
    text = re.sub(r"\bAbsatz\b", "Abs.", text)
    # "Nummer" -> "Nr."
    text = re.sub(r"\bNummer\b", "Nr.", text)
    # "Artikel" -> "Art."
    text = re.sub(r"\bArtikel\b", "Art.", text)

    # Convert roman numerals after "Abs." and "Nr." and "S."
    text = re.sub(r"(?<=Abs\.\s)(I{1,3}V?|VI{0,3})\b", replace_roman, text)
    text = re.sub(r"(?<=Nr\.\s)(I{1,3}V?|VI{0,3})\b", replace_roman, text)
    text = re.sub(r"(?<=S\.\s)(I{1,3}V?|VI{0,3})\b", replace_roman, text)

    # Remove duplicate "Abs. X Abs. X" patterns
    text = re.sub(r"(Abs\.\s+\d+)\s+Abs\.\s+\d+", r"\1", text)

    # Clean up double spaces
    text = re.sub(r"  +", " ", text)

    return text


def clean_beck_references(text):
    """Remove beck-online specific references like (Rn. BECKRS Jahr 2022 Randnummer 52)."""
    text = re.sub(r"\s*\(Rn\.\s*BECKRS\s+Jahr\s+\d+\s+Randnummer\s+\d+(?:\s+und\s+BECKRS\s+Jahr\s+\d+\s+Randnummer\s+\d+)*\)", "", text)
    text = re.sub(r"\s*\(Rn\.\s*\d+(?:\s*(?:und|,)\s*\d+)*\)", "", text)
    # Also remove standalone "Rn. XX" references at end of sentences
    text = re.sub(r"\s*\(Rn\.[^)]*\)", "", text)
    return text


def remove_redaktionelle_leitsaetze(paragraphs):
    """Remove redaktionelle Leitsätze, keeping only amtliche ones."""
    result = []
    skip = False
    for p in paragraphs:
        p_lower = p.strip().lower()
        # Skip section headers
        if re.match(r"^(amtliche[r]?\s+)?leitsätz?e?:?\s*$", p_lower):
            skip = False
            continue
        if re.match(r"^redaktionelle[r]?\s+leitsätz?e?:?\s*$", p_lower):
            skip = True
            continue
        if re.match(r"^amtliche[r]?\s+leitsatz:?\s*$", p_lower):
            skip = False
            continue
        if re.match(r"^leitsatz\s*$", p_lower):
            continue
        # If in redaktionell section, check for "(redaktioneller Leitsatz)" marker
        if "(redaktioneller Leitsatz)" in p.lower():
            continue
        if "(Leitsätze der Redaktion)" in p:
            continue
        if skip:
            continue
        result.append(p)
    return result


def clean_leitsatz_text(text):
    """Full cleanup pipeline for a Leitsatz text."""
    text = clean_beck_references(text)
    text = clean_gesetzesverweise(text)
    # Remove trailing/leading whitespace per line
    lines = [l.strip() for l in text.split("\n")]
    text = "\n".join(lines)
    # Remove empty lines at start/end
    text = text.strip()
    return text


def build_note_html(paragraphs):
    """Build a Zotero note HTML from cleaned paragraphs."""
    parts = []
    for p in paragraphs:
        p = p.strip()
        if p:
            parts.append(f"<p>{p}</p>")
    if not parts:
        return None
    return '<div class="zotero-note znv1"><h2>Leitsätze</h2>' + "".join(parts) + "</div>"


def parse_note_paragraphs(note_html):
    """Extract paragraphs from a note HTML."""
    from html.parser import HTMLParser

    class ParagraphExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paragraphs = []
            self.current = []
            self.in_p = False
            self.skip_heading = False

        def handle_starttag(self, tag, attrs):
            if tag in ("h2", "h3"):
                self.skip_heading = True
            if tag == "p":
                self.in_p = True
                self.current = []

        def handle_endtag(self, tag):
            if tag in ("h2", "h3"):
                self.skip_heading = False
            if tag == "p" and self.in_p:
                self.in_p = False
                text = "".join(self.current).strip()
                if text:
                    self.paragraphs.append(text)

        def handle_data(self, data):
            if self.in_p and not self.skip_heading:
                self.current.append(data)

    p = ParagraphExtractor()
    p.feed(note_html)
    return p.paragraphs


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
        """INSERT INTO items (itemID, itemTypeID, libraryID, key, version, synced, dateAdded, dateModified, clientDateModified)
        VALUES (?, ?, ?, ?, 0, 0, datetime('now'), datetime('now'), datetime('now'))""",
        (next_id, note_type_id, library_id, key),
    )
    c.execute(
        "INSERT INTO itemNotes (itemID, parentItemID, note, title) VALUES (?, ?, ?, ?)",
        (next_id, parent_item_id, note_html, title),
    )
    return next_id


# New Leitsätze from web research
NEW_LEITSAETZE = {
    # KG, 17.7.2024 - 22 W 25/24
    20: [
        "Eine nach österreichischem Recht erfolgte notarielle Online-Beglaubigung einer Handelsregisteranmeldung ist nicht als der deutschen Beglaubigung mittels Videokommunikation nach § 40a BeurkG gleichwertig anzuerkennen.",
    ],
    # BSG, 20.07.2023 - B 12 BA 1/23 R
    21: [
        "Stellt sich die Tätigkeit einer natürlichen Person nach deren tatsächlichem Gesamtbild als abhängige Beschäftigung dar, ist ein sozialversicherungspflichtiges Beschäftigungsverhältnis nicht deshalb ausgeschlossen, weil Verträge nur zwischen dem Auftraggeber und einer Kapitalgesellschaft bestehen, deren alleiniger Geschäftsführer und Gesellschafter die natürliche Person ist.",
    ],
    # ArbG München, 18.01.2023 - 20 Ca 7325/22 (first instance of LAG München 5 Sa 98/23)
    # No separate Leitsatz found online - this is the first instance
    29: None,
    # LAG München, 07.02.2024 - 5 Sa 98/23
    32: [
        "Die Regelung eines sukzessiven Verfalls bereits ausübbar gewordener (gevesteter) virtueller Optionen nach Beendigung des Arbeitsverhältnisses ist zulässig und benachteiligt den Arbeitnehmer nicht unangemessen.",
    ],
    # LAG Berlin-Brandenburg, 22.05.2024 - 26 Ta (Kost) 6096/23
    # No Leitsatz found
    33: None,
    # OLG München, 5.4.2023 - 7 U 6538/20
    45: [
        "1. Eine Stimmabgabe kann nach ihrem Zugang beim Versammlungsleiter nicht mehr widerrufen werden, unabhängig davon, ob ein wichtiger Grund für die Änderung des Abstimmungsverhaltens vorliegt, da es sich bei der Stimmabgabe um eine Willenserklärung i.S.d. § 130 Abs. 1 BGB handelt und deren Widerruf nach Zugang beim Erklärungsempfänger gem. § 130 Abs. 1 S. 2 BGB grundsätzlich nicht möglich ist.",
        "2. Da es sich bei § 873 Abs. 2, § 929 BGB um eine Ausnahmeregelung zu § 130 Abs. 1 BGB handelt, ist diese eng auszulegen und ihr Anwendungsbereich nicht auf andere Rechtsgeschäfte auszudehnen. Sie gilt auch nur für das dingliche Vollzugsgeschäft, nicht aber für die zugrunde liegende schuldrechtliche Verpflichtung.",
    ],
    # LG Frankfurt a. M., 23.10.2023 - 3-02 O 56/22
    # Not found online
    57: None,
    # BGH, 15.9.2023 - V ZR 77/22
    64: [
        "Der Verkäufer eines bebauten Grundstücks, der dem Käufer Zugriff auf einen Datenraum mit Unterlagen und Informationen zu der Immobilie gewährt, erfüllt hierdurch seine Aufklärungspflicht nur, wenn und soweit er aufgrund der Umstände die berechtigte Erwartung haben kann, dass der Käufer durch Einsichtnahme in den Datenraum Kenntnis von dem offenbarungspflichtigen Umstand erlangen wird.",
    ],
    # OLG München, 23.01.2012 - 31 Wx 457/11
    85: [
        "1. Beim genehmigten Kapital einer GmbH nach § 55a GmbHG kann die Entscheidung über den Ausschluss des Bezugsrechts der Gesellschafter auf die Geschäftsführung übertragen werden.",
        "2. Die Geschäftsführung kann zugleich ermächtigt werden, die Satzung entsprechend anzupassen.",
    ],
    # OLG Bremen, 26.06.2025 - 2 W 56/24
    # Not found online (too recent + captcha)
    342: None,
    # OLG München, 15.06.2020 - 32 Wx 140/20 Kost
    # Not found online
    345: None,
}


def main():
    conn = sqlite3.connect(ZOTERO_DB)
    c = conn.cursor()

    c.execute("SELECT collectionID FROM collections WHERE collectionName = ?", (COLLECTION_NAME,))
    col_id = c.fetchone()[0]

    c.execute("""
        SELECT ci.itemID FROM collectionItems ci
        JOIN items i ON ci.itemID = i.itemID
        WHERE ci.collectionID = ? AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
    """, (col_id,))
    item_ids = [r[0] for r in c.fetchall()]

    c.execute("SELECT fieldID, fieldName FROM fields")
    field_map = dict(c.fetchall())

    updated = 0
    created = 0
    skipped = 0

    for iid in item_ids:
        c.execute("""SELECT fieldID, value FROM itemDataValues
            JOIN itemData ON itemData.valueID = itemDataValues.valueID
            WHERE itemData.itemID = ?""", (iid,))
        fields = {field_map.get(r[0]): r[1] for r in c.fetchall()}
        name = f"{fields.get('court', '?')} {fields.get('docketNumber', '?')}"

        # Check for existing Leitsätze note
        c.execute("SELECT itemID, note FROM itemNotes WHERE parentItemID = ? AND title = 'Leitsätze'", (iid,))
        existing = c.fetchone()

        if existing:
            note_id, note_html = existing
            # Clean up existing note
            paragraphs = parse_note_paragraphs(note_html)
            paragraphs = remove_redaktionelle_leitsaetze(paragraphs)
            paragraphs = [clean_leitsatz_text(p) for p in paragraphs]
            paragraphs = [p for p in paragraphs if p]  # remove empty

            new_html = build_note_html(paragraphs)
            if new_html and new_html != note_html:
                c.execute("UPDATE itemNotes SET note = ? WHERE itemID = ?", (new_html, note_id))
                print(f"  UPDATED: {name}")
                updated += 1
            else:
                print(f"  OK (no change): {name}")
        elif iid in NEW_LEITSAETZE:
            ls = NEW_LEITSAETZE[iid]
            if ls is None:
                print(f"  SKIP (no data found online): {name}")
                skipped += 1
                continue
            paragraphs = [clean_leitsatz_text(p) for p in ls]
            new_html = build_note_html(paragraphs)
            if new_html:
                note_id = create_note(conn, iid, new_html)
                print(f"  CREATED note {note_id}: {name}")
                created += 1
        else:
            print(f"  SKIP (no existing note, no new data): {name}")
            skipped += 1

    conn.commit()
    conn.close()
    print(f"\nDone: {updated} updated, {created} created, {skipped} skipped")


if __name__ == "__main__":
    main()
