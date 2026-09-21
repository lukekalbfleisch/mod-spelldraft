#!/usr/bin/env python3
"""Snapshot live `spell_dbc` rows into a JSON manifest of raw DBC field values.

For a spell that only ever got a `spell_dbc` row (no native `Spell.dbc` record
- see tools/spell_dbc_override.py's docstring on why an override tool can't
create one), the client can't render or cast it: DBCDatabaseLoader adds or
replaces `Spell.dbc` records from `spell_dbc` positionally, but that only
helps the server, the only thing that reads the DB table. The fix is a real
Spell.dbc record, and the least error-prone source for its ~230 fields is the
row this core already runs against - not a hand-typed spec that could drift
from it (the exact trap spell_dbc_override.py's docstring warns about).

This script reads that row, in `spell_dbc`'s own column order (which is the
DBC field order - see broaden_talent_scoping.py's `load_columns`), and
converts each value to the signed int32 a DBC record field actually is:
float columns get bit-reinterpreted, unsigned columns get two's-complement
wrapped, text columns get mysql --batch's escaping undone. The result is a
manifest `tools/standalone_client_spells.json` that build_client_patch.py's
main() reads and appends to Spell.dbc verbatim (same {row, string_fields}
shape as client_patch_manifest.json's model-table entries, so it reuses
main()'s existing append_manifest_rows) - build_client_patch.py itself never
talks to the DB, matching how every other input it takes is a pre-baked JSON
file, not a live query.

Usage:
  python3 tools/extract_live_spell_dbc_rows.py --spell 990201 --why "..."
  python3 tools/extract_live_spell_dbc_rows.py --spell 990201 --spell 990202
"""

import argparse
import json
import os
import struct
import subprocess
import sys

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(MODULE_ROOT, "tools/standalone_client_spells.json")
DB_CONTAINER = "ac-database"
TABLE = "spell_dbc"
TEXT_TYPES = frozenset({"varchar", "char", "text", "tinytext", "mediumtext", "longtext"})

# Same anchors spell_dbc_override.py checks - a schema/field-order change
# fails loudly here too, instead of writing a row with fields in the wrong slots.
FIELD_ANCHORS = {"SpellClassSet": 208, "EffectAura_1": 95, "Name_Lang_enUS": 136}

_BATCH_ESCAPES = {"0": "\0", "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}


def unescape_batch(s):
    """Undo mysql --batch's backslash-escaping of \\0, \\, tab and newline."""
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] in _BATCH_ESCAPES:
            out.append(_BATCH_ESCAPES[s[i + 1]])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def run_query(query):
    cmd = ["docker", "exec", DB_CONTAINER, "mysql", "-uroot", "-ppassword",
           "acore_world", "--batch", "-e", query]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"error querying the DB (is {DB_CONTAINER} up?): {result.stderr.strip()}")
    lines = result.stdout.rstrip("\n").split("\n")
    if not lines or not lines[0]:
        return []
    headers = lines[0].split("\t")
    return [dict(zip(headers, line.split("\t"))) for line in lines[1:]]


def load_columns():
    """[(name, data_type, unsigned)] in DBC field order."""
    rows = run_query(
        "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA = 'acore_world' AND TABLE_NAME = '{TABLE}' ORDER BY ORDINAL_POSITION"
    )
    return [(row["COLUMN_NAME"], row["DATA_TYPE"], "unsigned" in row["COLUMN_TYPE"])
            for row in rows]


def to_dbc_int(raw, data_type, unsigned):
    """A `spell_dbc` column's text value (mysql --batch output) as a signed
    int32 DBC field - the inverse of spell_dbc_override.py's `apply_sets`."""
    if data_type == "float":
        return struct.unpack("<i", struct.pack("<f", float(raw)))[0]
    value = int(raw)
    if unsigned and value >= (1 << 31):
        value -= 1 << 32
    return value


def build_manifest_entry(spell_id, db_row, columns, why):
    row, string_fields = [], []
    for index, (name, data_type, unsigned) in enumerate(columns):
        if data_type in TEXT_TYPES:
            row.append(unescape_batch(db_row[name]))
            string_fields.append(index)
        else:
            row.append(to_dbc_int(db_row[name], data_type, unsigned))
    return {"id": spell_id, "why": why, "row": row, "string_fields": string_fields}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spell", type=int, action="append", required=True,
                        help="spell id to snapshot from the live spell_dbc (repeatable)")
    parser.add_argument("--why", required=True,
                        help="one-line reason, stored in the manifest for future readers")
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    columns = load_columns()
    for name, expected in FIELD_ANCHORS.items():
        index = next((i for i, (n, _, _) in enumerate(columns) if n == name), None)
        if index != expected:
            raise SystemExit(f"column layout changed: {name} is at {index}, expected {expected}")

    ids = sorted(set(args.spell))
    col_list = ", ".join(f"`{name}`" for name, _, _ in columns)
    live = {int(r["ID"]): r for r in run_query(
        f"SELECT {col_list} FROM `{TABLE}` WHERE ID IN ({', '.join(str(i) for i in ids)})")}
    missing = sorted(set(ids) - set(live))
    if missing:
        raise SystemExit(f"no spell_dbc row for: {missing}")

    manifest = {"spells": []}
    if os.path.exists(args.out):
        manifest = json.loads(open(args.out, encoding="utf-8").read())
    by_id = {entry["id"]: entry for entry in manifest["spells"]}
    for spell_id in ids:
        by_id[spell_id] = build_manifest_entry(spell_id, live[spell_id], columns, args.why)
    manifest["spells"] = [by_id[i] for i in sorted(by_id)]

    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print(f"wrote {args.out} ({len(ids)} spell(s): {ids})", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
