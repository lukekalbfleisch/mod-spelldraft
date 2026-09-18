#!/usr/bin/env python3
"""Broaden class-scoped talent spellmods (Phase 1d, Tier 2 policy).

Tier 2 talents (cooldowns, cast times, duration, range, charges) have no
per-school aura lever, so the only ways to stop them being class-scoped are
"drop SpellFamilyName" or "leave them class-locked". The chosen policy is
**drop the family**, but only for the chains whose scope is the whole class
family -- the ones that read like a spec ("your Arcane spells", "your Fire
spells") rather than like one spell.

Why the split matters: the engine widens a familyless spellmod *completely*.
`SpellInfo::IsAffected` returns true on a zero family before it ever looks at
the mask, so a familyless mod reaches every spell the character casts. That is
the intended outcome for `Burning Soul` / `Flame Throwing` / `Ice Floes`, but
for a one-spell talent it is destructive -- `Soul Warding` is a flat -4s
cooldown on Power Word: Shield, and broadening it means -4s on *every*
cooldown the character has. So one-bit masks are left alone, which also keeps
`Improved <spell>` talents meaning what their tooltips say.

Policy in one line: a Tier 2 chain is broadened when its classmask has more
than one bit. `--scope all` overrides that and broadens every Tier 2 chain.

Mechanism: a `spell_dbc` override row that is a copy of the spell with
`SpellClassSet` set to 0. The core loads `Spell.dbc` and then lets `spell_dbc`
replace rows wholesale (`DBCStore.cpp` -> `DBCDatabaseLoader`, which walks the
DBC format string and reads `SELECT * ... ORDER BY ID DESC` positionally, so a
row must carry every column). Text columns are emitted empty on purpose: the
loader treats an empty string as "not overridden", which preserves the spell's
name and tooltip without having to resolve the DBC string pool.

The tooltips are a known, deliberate debt: these talents' text still says
"your <class> spells". Rewording them needs the client `Spell.dbc` (i.e. a
`patch-P.mpq` rebuild via tools/build_client_patch.py) and the user's
client-effective DBCs, so it is left to a batch with the client patch. The
generated SQL lists every affected talent in a comment as that batch's todo.

Usage:
  python3 tools/broaden_talent_scoping.py                 # write the SQL
  python3 tools/broaden_talent_scoping.py --scope all     # broaden all of tier 2
  python3 tools/broaden_talent_scoping.py --check         # drift check vs the DB
  python3 tools/broaden_talent_scoping.py --out /tmp/x.sql
"""

import argparse
import collections
import json
import os
import struct
import subprocess
import sys

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(MODULE_ROOT, "tools"))

from build_client_patch import Dbc, SF_AURA, SF_FAMILY  # noqa: E402
from classify_talent_synergy import (  # noqa: E402
    MANIFEST_PATH, SPELLMOD_LEVERS, ADD_FLAT_MODIFIER, ADD_PCT_MODIFIER,
    classify_chains, derive_school_mask_auras, load_chains, load_spells, parse_enum,
)

CORE_ROOT = os.path.join(os.path.dirname(os.path.dirname(MODULE_ROOT)), "src", "server")
DB_CONTAINER = "ac-database"
DEFAULT_OUT = os.path.join(MODULE_ROOT, "data/sql/db-world/33_broad_talent_scoping.sql")
TABLE = "spell_dbc"


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
    """[(name, data_type, unsigned)] in DBC field order - the loader maps them positionally."""
    rows = run_query(
        "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA = 'acore_world' AND TABLE_NAME = '{TABLE}' ORDER BY ORDINAL_POSITION"
    )
    return [(row["COLUMN_NAME"], row["DATA_TYPE"], "unsigned" in row["COLUMN_TYPE"])
            for row in rows]


TEXT_TYPES = frozenset({"varchar", "char", "text", "tinytext", "mediumtext", "longtext"})


def mask_bits(mask):
    return sum(bin(value & 0xFFFFFFFF).count("1") for value in mask)


def worst_tier(effects):
    """A chain is tier N when its worst spellmod op is N."""
    return max(SPELLMOD_LEVERS.get(e["misc"], ("3", None))[0] for e in effects)


def select_chains(results, scope):
    """The Tier 2 chains the policy broadens, plus why each was kept or skipped."""
    selected, skipped_narrow, skipped_other = [], [], collections.Counter()
    for result in results:
        if result["label"] != "needs-redesign" or result["group"] != "class":
            continue
        scoped = [e for e in result["effects"] if e["verdict"] == "spellmod-class-scoped"]
        if not scoped:
            continue
        if worst_tier(scoped) != "2":
            skipped_other[f"tier {worst_tier(scoped)}"] += 1
            continue
        bits = max(mask_bits(e["mask"]) for e in scoped)
        if bits > 1 or scope == "all":
            selected.append((result, scoped, bits))
        else:
            skipped_narrow.append((result, bits))
    return selected, skipped_narrow, skipped_other


def collect_spells(selected, spells):
    """{spellId: {'talent': chain, 'bits': n}} for spells carrying a scoped spellmod.

    Only the rank spells that actually hold an ADD_*_MODIFIER aura with a class
    family are touched; a spell's SpellClassSet is cleared once even if several
    of its effects (or several chains) point at it.
    """
    affected = {}
    for result, scoped, bits in selected:
        for spell_id in result["ranks"]:
            row = spells.get(spell_id)
            if not row:
                continue
            if not any(row[SF_AURA + i] in (ADD_FLAT_MODIFIER, ADD_PCT_MODIFIER)
                       and row[SF_FAMILY] != 0 for i in range(3)):
                continue
            affected.setdefault(spell_id, {"talent": result, "bits": bits})
    return affected


def sql_values(row, columns, class_set_index):
    """One DBC record as SQL values, with SpellClassSet cleared.

    Text columns are emitted as '' because the loader keeps the DBC's own value
    for an empty string, which avoids resolving the string pool here.
    """
    out = []
    for index, (_, data_type, unsigned) in enumerate(columns):
        if index == class_set_index:
            out.append("0")
        elif data_type in TEXT_TYPES:
            out.append("''")
        elif data_type == "float":
            out.append(repr(round(struct.unpack("<f", struct.pack("<i", row[index]))[0], 6)))
        elif unsigned:
            # The DBC read is signed; mask/flag words are raw bit patterns, so a
            # negative value has to be widened or MySQL rejects it as out of range
            # for the column's `int unsigned` type.
            bits = 64 if data_type == "bigint" else 32
            out.append(str(row[index] & ((1 << bits) - 1)))
        else:
            out.append(str(row[index]))
    return out


def render_sql(affected, spells, columns, scope, dbc_path):
    """The full SQL document: header, per-talent todo list, then one row per spell."""
    class_set_index = next(i for i, (name, _, _) in enumerate(columns) if name == "SpellClassSet")
    ids = sorted(affected)
    by_talent = collections.defaultdict(list)
    for spell_id in ids:
        by_talent[affected[spell_id]["talent"]["name"]].append(spell_id)

    lines = []
    add = lines.append
    add("-- Broadened talent scoping: drop the class family from the talents whose scope")
    add("-- was a whole class ('your Arcane spells') rather than a single spell.")
    add("--")
    add("-- Phase 1d Tier 2 policy. A talent whose spellmod uses SPELLMOD_COOLDOWN,")
    add("-- CAST_TIME, DURATION, RANGE, CHARGES and friends has no per-school aura lever,")
    add("-- so the choice is 'universal' or 'class-locked'. These are universal now.")
    add("--")
    add("-- Mechanism: a spell_dbc override copying the spell with SpellClassSet = 0.")
    add("-- SpellInfo::IsAffected returns true on a zero family BEFORE it reads")
    add("-- EffectSpellClassMask, so the mod stops being scoped to one class's spellbook")
    add("-- and applies to every spell the character casts. Text columns are emitted")
    add("-- empty because the loader treats '' as 'not overridden', preserving each")
    add("-- spell's name and tooltip.")
    add("--")
    add(f"-- Scope: {scope} ({len(affected)} spells)")
    add("-- Regenerate with:")
    add(f"--   python3 tools/broaden_talent_scoping.py{' --scope all' if scope == 'all' else ''}")
    add(f"-- Read from Spell.dbc: {dbc_path}")
    add("--")
    add("-- REVERT: DELETE FROM `spell_dbc` WHERE `ID` IN (...the ids below...);")
    add("--")
    add("-- Tooltip debt: these tooltips still name a class and now understate their")
    add("-- scope. Rewording needs the client Spell.dbc (patch-P.mpq via")
    add("-- tools/build_client_patch.py), so it belongs to the next client-patch batch:")
    for name in sorted(by_talent):
        add(f"--   {name}")
    add("")
    add(f"DELETE FROM `{TABLE}` WHERE `ID` IN ({', '.join(str(i) for i in ids)});")
    add("")
    column_list = ", ".join(f"`{name}`" for name, _, _ in columns)
    for offset in range(0, len(ids), 20):
        chunk = ids[offset:offset + 20]
        add(f"INSERT INTO `{TABLE}`")
        add(f"  ({column_list})")
        add("VALUES")
        rows = []
        for spell_id in chunk:
            values = sql_values(spells[spell_id], columns, class_set_index)
            rows.append(f"  ({spell_id}, " + ", ".join(values[1:]) + ")")
        add(",\n".join(rows) + ";")
        add("")
    return "\n".join(lines) + "\n"


def render_check(affected, spells):
    """Compare the DB's overrides with what the policy wants."""
    ids = sorted(affected)
    rows = run_query(
        f"SELECT ID, SpellClassSet FROM `{TABLE}` WHERE ID IN ({', '.join(str(i) for i in ids)})"
    )
    current = {int(r["ID"]): int(r["SpellClassSet"]) for r in rows}
    missing = [i for i in ids if i not in current]
    stale = [i for i, family in current.items() if family != 0]
    return missing, stale


# ============================================================================
# Entry point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dbc", help="Spell.dbc to read (default: copy it from the "
                                      "running worldserver container)")
    parser.add_argument("--scope", choices=("broad", "all"), default="broad",
                        help="broad: only Tier 2 chains whose classmask covers more than "
                             "one spell (default). all: every Tier 2 chain.")
    parser.add_argument("--out", default=DEFAULT_OUT, help=f"SQL output path (default: "
                                                           f"{os.path.relpath(DEFAULT_OUT, MODULE_ROOT)})")
    parser.add_argument("--check", action="store_true",
                        help="verify the live spell_dbc matches this policy instead of writing")
    args = parser.parse_args()

    from classify_talent_synergy import resolve_dbc  # local import: only needed here

    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8"))
    tab_classes = {tab["tabId"]: tab["class"].capitalize() for tab in manifest["tabs"]}

    chains = load_chains(None)
    wanted = {spell_id for _, _, _, ranks in chains for spell_id in ranks}
    dbc_path = resolve_dbc(args.dbc)
    dbc, spells = load_spells(dbc_path, wanted)

    aura_names = parse_enum(os.path.join(CORE_ROOT, "game/Spells/Auras/SpellAuraDefines.h"),
                            ["SPELL_AURA_"])
    results = classify_chains(chains, dbc, spells, aura_names, derive_school_mask_auras(),
                              tab_classes)

    selected, skipped_narrow, skipped_other = select_chains(results, args.scope)
    affected = collect_spells(selected, spells)

    print(f"policy scope          : {args.scope}", file=sys.stderr)
    print(f"tier 2 chains matched : {len(selected)}", file=sys.stderr)
    print(f"tier 2 left narrow    : {len(skipped_narrow)} "
          f"(one-spell talents, e.g. {', '.join(r['name'] for r, _ in skipped_narrow[:3])})",
          file=sys.stderr)
    print(f"chains in other tiers : {dict(skipped_other)}", file=sys.stderr)
    print(f"spells to broaden     : {len(affected)}", file=sys.stderr)

    if args.check:
        missing, stale = render_check(affected, spells)
        if missing or stale:
            print(f"DRIFT: {len(missing)} spell(s) have no override, {len(stale)} keep a family",
                  file=sys.stderr)
            print(f"  missing: {missing[:10]}", file=sys.stderr)
            print(f"  stale  : {stale[:10]}", file=sys.stderr)
            return 1
        print("policy is applied: every affected spell has SpellClassSet = 0", file=sys.stderr)
        return 0

    sql = render_sql(affected, spells, load_columns(), args.scope, dbc_path)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(sql)
    print(f"wrote {args.out} ({len(sql) // 1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
