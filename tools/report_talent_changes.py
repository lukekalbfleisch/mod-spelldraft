#!/usr/bin/env python3
"""List the talents already rescoped by Phase 1d, in plain language.

Two policies have shipped, one SQL file each:

  33_broad_talent_scoping.sql   Tier 2 - the class scope is dropped, so the
                                talent reaches every spell the character has
  34_school_scope_tier1.sql     Tier 1 - the class scope became a school scope
                                ("your Fire and Frost spells"), which the
                                character's second class can share

This tool explains *what changed* for each affected spell, which is what makes
the outcome reviewable: a diff of the SQL is unreadable, and the raw `spell_dbc`
fields (`EffectAura_2 = 71`, `EffectMiscValue_2 = 33`) say nothing about intent.

Both sides are read from the running stack - the "before" from the server's own
`Spell.dbc` and the "after" from the live `spell_dbc` - so the report describes
what the server actually serves, not what the generator intended. It checks that
too: each override may differ from stock only in `SpellClassSet` and its effect
slots, so a bug that moves an unrelated column shows up as a failed self-check.

What is NOT here: the tooltips. They still read like the original class scopes,
which is a tracked debt (see the header of each SQL file) left to the next client
patch, because rewording them needs `Spell.dbc` on the client.

Usage:
  python3 tools/report_talent_changes.py                   # write docs/TALENT_CHANGES.md
  python3 tools/report_talent_changes.py --out /tmp/x.md
  python3 tools/report_talent_changes.py --dbc /tmp/Spell.dbc
"""

import argparse
import collections
import json
import os
import re
import struct
import sys

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(MODULE_ROOT, "tools"))

from build_client_patch import (  # noqa: E402
    Dbc, SF_AURA, SF_BASEPOINTS, SF_DESC, SF_FAMILY, SF_MISCA, SF_NAME,
)
from classify_talent_synergy import (  # noqa: E402
    MANIFEST_PATH, SPELLMOD_OP_NAMES, dbc_string, load_chains, resolve_dbc, run_query,
)

DEFAULT_OUT = os.path.join(MODULE_ROOT, "docs", "TALENT_CHANGES.md")
SQL_DIR = os.path.join(MODULE_ROOT, "data", "sql", "db-world")
TABLE = "spell_dbc"

# The two shipped policies, in the order they are presented. The file an id came
# from is the policy that touched it, and they are disjoint by design (asserted
# in main), so an id can only belong to one.
POLICIES = [
    ("33_broad_talent_scoping.sql", "T2",
     "`scope dropped` - the class scope is gone; the mod reaches every spell"),
    ("34_school_scope_tier1.sql", "T1",
     "`school scope` - the class scope became a school scope, so the character's "
     "second class can share it"),
]

SCHOOLS = {1: "Physical", 2: "Holy", 4: "Fire", 8: "Nature", 16: "Frost",
           32: "Shadow", 64: "Arcane"}

# Aura id -> how to say what it does. Only the levers these two policies emit.
AURA_PHRASES = {
    72: lambda amt, misc: f"{amt:+d}% cost for {school_phrase(misc)}",
    73: lambda amt, misc: f"{amt:+d} cost for {school_phrase(misc)}",
    79: lambda amt, misc: f"{amt:+d}% damage for {school_phrase(misc)}",
    71: lambda amt, misc: f"{amt:+d}% crit chance for {school_phrase(misc)}",
    163: lambda amt, misc: f"{amt:+d}% crit damage for {school_phrase(misc)}",
    199: lambda amt, misc: f"{amt:+d}% hit for {school_phrase(misc)}",
    10: lambda amt, misc: f"{amt:+d}% threat for {school_phrase(misc)}",
    136: lambda amt, misc: f"{amt:+d}% healing from any spell",
    235: lambda amt, misc: f"{amt:+d}% dispel resistance (any spell)",
}


def school_phrase(misc):
    """Every school (127, the broad fallback) versus the named ones."""
    if misc == 127:
        return "every spell"
    names = "+".join(name for bit, name in SCHOOLS.items() if misc & bit)
    return f"{names or 'schoolless'} spells"


def describe_aura(aura, misc, amount):
    phrase = AURA_PHRASES.get(aura)
    return phrase(amount, misc) if phrase else f"aura {aura} (school {misc}) amount {amount}"


def describe_mod(aura, misc, amount):
    """The original class-scoped spellmod, named by its SpellModOp."""
    if aura in (107, 108):
        leaf = "pct" if aura == 108 else "flat"
        return f"{SPELLMOD_OP_NAMES.get(misc, misc)} mod {amount:+d} ({leaf})"
    return f"aura {aura} amount {amount}"
def parse_policy_ids(path):
    """The ids a policy file declares in its DELETE statement.

    Comments are stripped first: the header also contains a `DELETE ... IN (...)`
    example whose list is a literal `...`, which is not valid SQL.
    """
    with open(path, encoding="utf-8") as handle:
        body = "\n".join(line for line in handle.read().split("\n")
                         if not line.startswith("--"))
    match = re.search(r"DELETE FROM `spell_dbc` WHERE `ID` IN \(([^)]*)\);", body)
    if not match:
        raise SystemExit(f"error: no DELETE statement found in {path}")
    return [int(value) for value in match.group(1).split(", ")]


def load_stock(dbc_path):
    """(dbc, {id: row}) for every spell, as the server's own Spell.dbc has it."""
    dbc = Dbc(dbc_path)
    rows = {}
    for index in range(dbc.recs):
        row = struct.unpack_from(f"<{dbc.fields}i", dbc.records, index * dbc.recsize)
        rows[row[0]] = row
    return dbc, rows


def load_overrides(ids):
    """{id: {column: value}} from the live spell_dbc."""
    placeholders = ",".join(str(spell_id) for spell_id in ids)
    rows = run_query(f"SELECT * FROM `{TABLE}` WHERE `ID` IN ({placeholders})")
    return {int(row["ID"]): row for row in rows}


def load_columns():
    """[(name, data_type)] in DBC field order; the loader maps them positionally."""
    rows = run_query("SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
                     f"WHERE TABLE_SCHEMA = 'acore_world' AND TABLE_NAME = '{TABLE}' "
                     "ORDER BY ORDINAL_POSITION")
    return [(row["COLUMN_NAME"], row["DATA_TYPE"]) for row in rows]


# The columns a policy may rewrite beyond the scope itself.
EFFECT_COLUMNS = frozenset(
    f"{field}_{slot}"
    for field in ("Effect", "EffectAura", "EffectMiscValue", "EffectBasePoints")
    for slot in (1, 2, 3))
ALLOWED = {"T1": EFFECT_COLUMNS, "T2": frozenset()}
INTEGER_TYPES = frozenset({"tinyint", "smallint", "mediumint", "int", "bigint"})


def entry_for(spell_id, row, override, policy, owner):
    """What changed for one spell, as a list of before -> after strings."""
    class_name, talent_name, tooltip = owner
    family_before = row[SF_FAMILY]
    items = []
    for slot in range(3):
        old = (row[SF_AURA + slot], row[SF_MISCA + slot],
               row[SF_BASEPOINTS + slot] + 1)
        new = (int(override[f"EffectAura_{slot + 1}"]),
               int(override[f"EffectMiscValue_{slot + 1}"]),
               int(override[f"EffectBasePoints_{slot + 1}"]) + 1)
        if new[0] == 0:
            # A merged-away slot is only worth reporting when it held one of the
            # mods; slots that were already empty are noise.
            if old[0] in (107, 108):
                items.append(f"{describe_mod(old[0], old[1], old[2])} "
                             "-> folded into another effect")
            continue
        if old != new:
            items.append(f"{describe_mod(old[0], old[1], old[2])} -> "
                         f"{describe_aura(new[0], new[1], new[2])}")
    if family_before and int(override["SpellClassSet"]) == 0:
        # Tier 2 keeps its mods and only drops their reach; Tier 1 replaced them.
        mods = [item.split(" -> ")[0] for item in items if "folded into" not in item]
        if policy == "T2" and mods:
            items = [f"{', '.join(mods[:2])} -> the same mod, reaching every spell"]
        elif not items:
            items = [f"scope widened from {class_name} spells to every spell"]
    return dict(class_name=class_name, talent=talent_name, spell_id=spell_id,
                policy=policy, items=items, tooltip=tooltip)


def verify_overrides(columns, stock, overrides, policy_of):
    """Every column but the ones a policy owns must be identical to stock.

    This is what makes the report trustworthy. The SQL copies a whole DBC row, so
    a bug in the generator surfaces as an unrelated column moving - and that is
    not hypothetical: the first version of the Tier 1 tool summed the amounts of
    mods that shared an (aura, school) pair, which is exactly the kind of mistake
    only a field-level comparison catches.

    Two columns are skipped or normalised because their *representation* differs
    while their value does not:
      - floats, which the SQL formats as `1.0` where a DBC row stores raw bits;
      - the class masks, which are `int unsigned` in SQL but read signed from the
        DBC (`EffectSpellClassMaskA_1` -1591717888 is 2703249408), so both sides
        are compared modulo 2^32.
    """
    checked = [(index, name) for index, (name, data_type) in enumerate(columns)
               if data_type in INTEGER_TYPES]
    problems = []
    for spell_id, override in sorted(overrides.items()):
        row = stock[spell_id]
        allowed = ALLOWED[policy_of[spell_id]] | {"SpellClassSet"}
        for index, name in checked:
            if name in allowed:
                continue
            if (int(override[name]) & 0xFFFFFFFF) != (row[index] & 0xFFFFFFFF):
                problems.append((spell_id, name, row[index], override[name]))
    return checked, problems


def build_report(entries, dbc_path, checked, problems):
    by_class = collections.defaultdict(list)
    for entry in entries:
        by_class[entry["class_name"]].append(entry)
    spell_count = len(entries)
    talent_count = len({entry["talent"] for entry in entries})

    lines = ["# Talents changed so far (Phase 1d)", "",
             "Generated by `tools/report_talent_changes.py`, reading the live `spell_dbc`",
             f"and the server's `Spell.dbc` ({dbc_path}).", "",
             f"**{spell_count} spells across {talent_count} talents**, under two policies:",
             ""]
    for filename, _, description in POLICIES:
        lines.append(f"- `{filename}` - {description}")
    lines += ["",
              "A talent can appear under both policies when its ranks were split between",
              "them; the policy is decided per chain, not per spell.", "",
              "| class | spells | talents |", "|---|---:|---:|"]
    for class_name in sorted(by_class):
        rows = by_class[class_name]
        lines.append(f"| {class_name} | {len(rows)} | "
                     f"{len({entry['talent'] for entry in rows})} |")
    lines.append(f"| **total** | **{spell_count}** | **{talent_count}** |")

    lines += ["", "## One example per class", "",
              "The first example of each policy for that class - the same numbers and",
              "schools apply to every rank of the talent.", "",
              "| class | talent | policy | what changed |", "|---|---|---|---|"]
    for class_name in sorted(by_class):
        for policy in ("T1", "T2"):
            candidates = sorted((e for e in by_class[class_name]
                                 if e["policy"] == policy and e["items"]),
                                key=lambda entry: entry["talent"])
            if not candidates:
                continue
            entry = candidates[0]
            label = "school scope" if policy == "T1" else "scope dropped"
            lines.append(f"| {class_name} | {entry['talent']} | {label} | "
                         f"{entry['items'][0]} |")

    lines += ["", "## Every changed talent, by class", "",
              "One line per talent, described from its first changed rank (later ranks",
              "carry the same shape at higher amounts).", ""]
    for class_name in sorted(by_class):
        lines += [f"### {class_name}", ""]
        grouped = collections.defaultdict(list)
        for entry in sorted(by_class[class_name],
                            key=lambda e: (e["policy"], e["talent"], e["spell_id"])):
            grouped[entry["talent"]].append(entry)
        for talent, group in sorted(grouped.items()):
            ranks = len({entry["spell_id"] for entry in group})
            label = "school scope" if group[0]["policy"] == "T1" else "scope dropped"
            detail = "; ".join(group[0]["items"]) or "scope only"
            lines.append(f"- **{talent}** ({label}, {ranks} rank"
                         f"{'' if ranks == 1 else 's'}) - {detail}")
        lines.append("")

    lines += ["## Self-check", "",
              f"- {len(checked)} integer columns per row were compared against",
              "  `Spell.dbc`; only the scope and the rewritten effect slots differ: "
              f"**{'PASS' if not problems else 'FAIL'}**."]
    for spell_id, field, before, after in problems[:10]:
        lines.append(f"  - spell {spell_id}: `{field}` {before} -> {after}")
    lines += ["", "The tooltips still describe the original class scopes; rewording them",
              "is tracked in the header of each SQL file and needs the next client patch.",
              ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dbc", help="path to Spell.dbc (default: the server's own)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="path of the report to write")
    args = parser.parse_args()

    policy_of = {}
    for filename, code, _ in POLICIES:
        for spell_id in parse_policy_ids(os.path.join(SQL_DIR, filename)):
            if spell_id in policy_of:
                raise SystemExit(f"error: {filename} repeats a spell id from an earlier "
                                 f"policy: {spell_id}")
            policy_of[spell_id] = code

    dbc_path = resolve_dbc(args.dbc)
    dbc, stock = load_stock(dbc_path)
    overrides = load_overrides(sorted(policy_of))
    missing = sorted(set(policy_of) - set(overrides))
    if missing:
        raise SystemExit(f"error: {len(missing)} spell(s) are shipped in the SQL but "
                         f"absent from {TABLE} (is the server up and the SQL applied?): "
                         f"{missing[:5]}")

    # Talent name and class come from the chain each spell belongs to.
    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8"))
    tab_classes = {tab["tabId"]: tab["class"].capitalize() for tab in manifest["tabs"]}
    owners = {}
    for _, tab, _, ranks in load_chains(None):
        if not ranks:
            continue
        owners.update({spell_id: (tab_classes.get(tab, "?"),
                                  dbc_string(dbc, stock[ranks[0]][SF_NAME]),
                                  dbc_string(dbc, stock[ranks[0]][SF_DESC]))
                       for spell_id in ranks})

    columns = load_columns()
    checked, problems = verify_overrides(columns, stock, overrides, policy_of)
    entries = [entry_for(spell_id, stock[spell_id], overrides[spell_id],
                         policy_of[spell_id], owners.get(spell_id, ("?", "?", "")))
               for spell_id in sorted(overrides)]

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(build_report(entries, dbc_path, checked, problems))

    by_policy = collections.Counter(entry["policy"] for entry in entries)
    print(f"{len(entries)} spells, {len({e['talent'] for e in entries})} talents "
          f"(scope dropped: {by_policy['T2']}, school scope: {by_policy['T1']})")
    print(f"self-check: {len(checked)} integer columns compared per row, "
          f"{'clean' if not problems else str(len(problems)) + ' unexpected difference(s)'}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
