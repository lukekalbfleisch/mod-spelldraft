#!/usr/bin/env python3
"""
Single source of truth for the talent trees.

Before this script existed the talent data was hand-synced in four places
(`talent_dbc`, two copies of `LOCKED_TALENTS`, and the client's
`SpellData_Talents.lua`) with no generator - documented as the biggest gap in
`docs/TALENTS.md`. This script derives all of the generated artifacts from one
manifest plus the Talent.dbc dump, so they can no longer drift.

Inputs (sources of truth):
  - tools/talent_manifest.json            authored: tab -> class/spec, locked talents
  - data/sql/db-world/06_talent_dbc.sql   the Talent.dbc dump (chains, ranks, prereqs)

Outputs (rewritten in place):
  - wow-client/Interface/AddOns/SpellDraft/SpellData_Talents.lua
        SpellDraftTalentDB + SpellDraftTalentRankMap (whole file is generated)
  - lua/SpellDraft/spell_choice.lua        LOCKED_TALENTS (generated region)
  - wow-client/.../SpellBook.lua           LOCKED_TALENTS (generated region)
  - lua/spelldraft_config.lua              TALENT_TAB_CLASS (generated region)

Generated regions are delimited by BEGIN/END GENERATED markers, so re-running is
idempotent. Content outside those markers is never touched.

New talents authored as real spells still go through the existing client-patch
pipeline (tools/build_client_patch.py + eq_talent_pack.json); this script only
covers the Talent.dbc-derived artifacts.

Prerequisites:
  - Python 3.x only. No database needed: the chains are read from the committed
    SQL dump, so the script (and --check) runs anywhere.

Usage:
  python3 tools/generate_talent_data.py           # rewrite the outputs
  python3 tools/generate_talent_data.py --check   # verify the outputs are current (CI-friendly)
"""

import json
import os
import re
import sys

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MANIFEST_PATH = os.path.join(MODULE_ROOT, "tools/talent_manifest.json")
TALENT_DBC_SQL_PATH = os.path.join(MODULE_ROOT, "data/sql/db-world/06_talent_dbc.sql")

CLIENT_TALENT_DB_PATH = os.path.join(MODULE_ROOT, "wow-client/Interface/AddOns/SpellDraft/SpellData_Talents.lua")
SERVER_TALENTS_PATH = os.path.join(MODULE_ROOT, "lua/SpellDraft/spell_choice.lua")
CLIENT_SPELLBOOK_PATH = os.path.join(MODULE_ROOT, "wow-client/Interface/AddOns/SpellDraft/SpellBook.lua")
SERVER_CONFIG_PATH = os.path.join(MODULE_ROOT, "lua/spelldraft_config.lua")

# AzerothCore `Classes` ids. The manifest uses class names (readable, and they match
# the client's CLASS_ORDER); the server config wants the numeric id.
CLASS_IDS = {
    "WARRIOR": 1, "PALADIN": 2, "HUNTER": 3, "ROGUE": 4, "PRIEST": 5,
    "DEATHKNIGHT": 6, "SHAMAN": 7, "MAGE": 8, "WARLOCK": 9, "DRUID": 11,
}

GENERATOR = "tools/generate_talent_data.py"

# Sources of truth (documented here so the manifest stays short and lint-clean):
#   - tools/talent_manifest.json           authored: tab -> class/spec, locked talents
#   - data/sql/db-world/06_talent_dbc.sql  the Talent.dbc dump (chains, ranks, prereqs)

# Human-readable class names for the generated comments.
CLASS_LABELS = {
    "WARRIOR": "Warrior", "PALADIN": "Paladin", "HUNTER": "Hunter", "ROGUE": "Rogue",
    "PRIEST": "Priest", "DEATHKNIGHT": "Death Knight", "SHAMAN": "Shaman",
    "MAGE": "Mage", "WARLOCK": "Warlock", "DRUID": "Druid",
}

# Entries per line for the wrapped tables.
LOCKED_PER_LINE = 8
RANKMAP_PER_LINE = 8


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def load_manifest():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_talent_rows():
    """
    Parse the committed Talent.dbc dump into {talentId: {...}}.

    Columns: ID, TabID, TierID, ColumnIndex, SpellRank_1..9, PrereqTalent_1..3,
    PrereqRank_1..3, Flags, RequiredSpellID, CategoryMask_1..2. Rows are one per
    line, comma-separated, and the last row ends the statement with ';'.
    """
    sql = read(TALENT_DBC_SQL_PATH)
    rows = {}
    for match in re.finditer(r"^\(([0-9,]+)\)[,;]$", sql, re.M):
        fields = [int(value) for value in match.group(1).split(",")]
        ranks = [value for value in fields[4:13] if value > 0]
        if not ranks:
            continue

        rows[fields[0]] = {
            "tab": fields[1],
            "tier": fields[2],
            "col": fields[3],
            "ranks": ranks,
            "prereqTalents": [value for value in fields[13:16] if value > 0],
        }

    return rows


def allowed_tabs(manifest):
    """tabId -> (class, spec), in manifest order."""
    return {tab["tabId"]: (tab["class"], tab["spec"]) for tab in manifest["tabs"]}


def build_client_tables(rows, tabs):
    """
    Derive SpellDraftTalentDB and SpellDraftTalentRankMap from the dump.

    TalentDB is keyed by a chain's first-rank spell id; RankMap resolves every rank
    back to {firstRankSpellId, rankIndex}. Chains in tabs that are not in the
    manifest (the Hunter pet trees are deliberate) are skipped, matching the
    server's rule that an unmapped tab is not player-selectable.
    """
    talent_db = {}
    rank_map = {}

    for info in rows.values():
        mapping = tabs.get(info["tab"])
        if not mapping:
            continue

        cls, spec = mapping
        first_rank = info["ranks"][0]

        # The client only needs the parent's first-rank id; the dump stores the
        # prerequisite talent id, so translate it.
        prereq_first = 0
        if info["prereqTalents"]:
            parent = rows.get(info["prereqTalents"][0])
            if parent:
                prereq_first = parent["ranks"][0]

        talent_db[first_rank] = (cls, spec, info["tier"], info["col"], len(info["ranks"]), prereq_first)

        for index, spell_id in enumerate(info["ranks"], 1):
            rank_map[spell_id] = (first_rank, index)

    return talent_db, rank_map


def render_client_talent_file(talent_db, rank_map):
    lines = ["-- Auto-generated Talent Tree database for SpellDraft addon", "SpellDraftTalentDB = {"]
    for spell_id in sorted(talent_db):
        cls, spec, row, col, max_rank, prereq = talent_db[spell_id]
        lines.append(
            f'  [{spell_id}] = {{ class = "{cls}", spec = "{spec}", row = {row}, '
            f"col = {col}, maxRank = {max_rank}, prereqSpellId = {prereq} }},"
        )
    lines.append("}")
    lines.append("")
    lines.append("-- Auto-generated from talent_dbc: rank spell ID -> { firstRankSpellId, rankIndex }")
    lines.append("-- Lets the addon resolve ranks without name lookups (talent names collide across classes)")
    lines.append("SpellDraftTalentRankMap = {")

    cells = [f"[{spell_id}]={{{first},{index}}}" for spell_id, (first, index) in sorted(rank_map.items())]
    for start in range(0, len(cells), RANKMAP_PER_LINE):
        lines.append("  " + ", ".join(cells[start:start + RANKMAP_PER_LINE]) + ",")

    lines.append("}")
    return "\n".join(lines) + "\n"


def render_locked_talents(manifest):
    """The LOCKED_TALENTS table, identical for the server and the client."""
    lines = ["local LOCKED_TALENTS = {"]
    for cls, ids in manifest["lockedTalents"].items():
        lines.append(f"    -- {cls} ({len(ids)})")
        cells = [f"[{spell_id}] = true" for spell_id in ids]
        for start in range(0, len(cells), LOCKED_PER_LINE):
            lines.append("    " + ", ".join(cells[start:start + LOCKED_PER_LINE]) + ",")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_tab_class_table(manifest):
    """The server's talent_dbc.TabID -> class table, inside CONFIG."""
    tabs = manifest["tabs"]
    key_width = max(len(f"[{tab['tabId']}]") for tab in tabs) + 1

    lines = ["    TALENT_TAB_CLASS = {"]
    previous_class = None
    for tab in tabs:
        cls = tab["class"]
        if cls != previous_class:
            lines.append(f"        -- {CLASS_LABELS[cls]}")
            previous_class = cls
        key = f"[{tab['tabId']}]".ljust(key_width)
        value = f"{CLASS_IDS[cls]},".ljust(5)
        lines.append(f"        {key}= {value}-- {tab['spec']}")
    lines.append("    },")
    return "\n".join(lines) + "\n"


def patch_region(path, name, body, start_pattern, end_pattern, indent=""):
    """
    Replace a generated region in place, keeping the file's surrounding content.

    Regions are delimited by BEGIN/END GENERATED markers. The first run (a file that
    has no markers yet) locates the existing block with start_pattern/end_pattern and
    adds them; later runs replace strictly between the markers.
    """
    text = read(path)
    begin = indent + f"-- BEGIN GENERATED: {name} ({GENERATOR})"
    end = indent + f"-- END GENERATED: {name}"
    marked = begin + "\n" + body.rstrip("\n") + "\n" + end + "\n"

    if begin in text and end in text:
        head = text[:text.index(begin)]
        tail = text[text.index(end) + len(end):]
        tail = tail[1:] if tail.startswith("\n") else tail
        return head + marked + tail

    match = re.search(start_pattern + r".*?" + end_pattern + r"\n", text, re.S | re.M)
    if not match:
        raise SystemExit(f"Could not find the {name} block in {os.path.relpath(path, MODULE_ROOT)}")

    return text[:match.start()] + marked + text[match.end():]


def build_outputs():
    """Every generated artifact as it should appear on disk, keyed by path."""
    manifest = load_manifest()
    rows = load_talent_rows()
    tabs = allowed_tabs(manifest)

    unmapped = sorted({info["tab"] for info in rows.values() if info["tab"] not in tabs})
    if unmapped:
        print(
            f"note: TabID(s) {unmapped} are not in the manifest, so their chains are skipped "
            "(the Hunter pet trees 409/410/411 are expected here).",
            file=sys.stderr,
        )

    talent_db, rank_map = build_client_tables(rows, tabs)

    outputs = {
        CLIENT_TALENT_DB_PATH: render_client_talent_file(talent_db, rank_map),
        SERVER_TALENTS_PATH: patch_region(
            SERVER_TALENTS_PATH, "LOCKED_TALENTS",
            render_locked_talents(manifest),
            r"^local LOCKED_TALENTS = \{", r"^\}",
        ),
        CLIENT_SPELLBOOK_PATH: patch_region(
            CLIENT_SPELLBOOK_PATH, "LOCKED_TALENTS",
            render_locked_talents(manifest),
            r"^local LOCKED_TALENTS = \{", r"^\}",
        ),
        SERVER_CONFIG_PATH: patch_region(
            SERVER_CONFIG_PATH, "TALENT_TAB_CLASS",
            render_tab_class_table(manifest),
            r"^    TALENT_TAB_CLASS = \{", r"^    \},", indent="    ",
        ),
    }

    return outputs, talent_db, rank_map


def main():
    check_only = "--check" in sys.argv[1:]
    outputs, talent_db, rank_map = build_outputs()

    drifted = [path for path, expected in outputs.items() if read(path) != expected]

    if check_only:
        if drifted:
            print("Talent data is out of date, run tools/generate_talent_data.py:")
            for path in drifted:
                print("  " + os.path.relpath(path, MODULE_ROOT))
            return 1
        print(f"Talent data is current ({len(talent_db)} talents, {len(rank_map)} ranks).")
        return 0

    for path in drifted:
        write(path, outputs[path])
        print("updated " + os.path.relpath(path, MODULE_ROOT))

    if not drifted:
        print("Talent data already current.")
    else:
        print(f"{len(talent_db)} talents, {len(rank_map)} ranks.")

    return 0


if __name__ == "__main__":
    sys.exit(main())