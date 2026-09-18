#!/usr/bin/env python3
"""Classify every talent in the tree by whether its benefit crosses classes.

Phase 1d of the traditional-multiclass plan. The question this answers: with a
character holding two classes, does a talent bought in one class's tree do
anything for the *other* class's spells? The locked design decision is
"universal-school synergy" - talents must say "you deal 3% more Fire damage"
(all sources), never "your Destruction spells deal 3% more Fire damage".

THE RULE (verified against the core, not guessed):

  SpellMod auras (SPELL_AURA_ADD_FLAT_MODIFIER=107 / ADD_PCT_MODIFIER=108) are
  scoped by (SpellFamilyName, EffectSpellClassMask) of the *owning* spell:

    AuraEffect::CalculateSpellMod  (SpellAuraEffects.cpp:703)
        m_spellmod->mask = GetSpellInfo()->Effects[GetEffIndex()].SpellClassMask;

    SpellInfo::IsAffectedBySpellMod (SpellInfo.cpp:1357)
        affectSpell = GetSpellInfo(mod->spellId);        // the aura's own spell
        return IsAffected(affectSpell->SpellFamilyName, mod->mask);

    SpellInfo::IsAffected (SpellInfo.cpp)
        if (!familyName) return true;                    // family 0 => EVERY spell
        if (familyName != SpellFamilyName) return false;  // else same family only
        if (familyFlags && !(familyFlags & SpellFamilyFlags)) return false;

  So a spellmod whose spell has SpellFamilyName != 0 can only ever reach that
  one class's spells - a Fire Mage / Destruction Warlock buying "Fire Power"
  buffs the Mage half only. That is the SpellClassMask trap.

  Note the corollary: family == 0 means the mod applies to *every* spell and the
  EffectSpellClassMask is ignored entirely (`if (!familyName) return true`).

  Non-spellmod auras are NOT family-gated, with a handful of exceptions that do
  call AuraEffect::IsAffectedOnSpell (same IsAffected test) - those are listed in
  AURA_FAMILY_GATED below, derived from the core. Everything else either uses a
  school mask from EffectMiscValue (=> school-wide by construction; the aura
  types are derived from the core's `*ByMiscMask(SPELL_AURA_*)` call sites plus
  the MAX_SPELL_SCHOOL bit loops in the MOD_DAMAGE_DONE/MOD_HEALING_DONE
  handlers) or is a plain character stat/rating/percentage.

Inputs:
  - talent chains: live `talent_dbc` (default) or --talent-sql for the committed dump
  - spells: Spell.dbc from the running worldserver container (or --dbc PATH)
  - class names: tools/talent_manifest.json (tab -> class)
  - the rule sets + enum names: parsed out of src/server/ at run time

Usage:
  python3 tools/classify_talent_synergy.py                    # markdown report to stdout
  python3 tools/classify_talent_synergy.py --out docs/TALENT_SYNERGY.md
  python3 tools/classify_talent_synergy.py --json report.json
"""

import argparse
import collections
import json
import os
import re
import struct
import subprocess
import sys

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.abspath(os.path.join(MODULE_ROOT, "..", ".."))
CORE_ROOT = os.path.join(REPO_ROOT, "src", "server")

sys.path.insert(0, os.path.join(MODULE_ROOT, "tools"))
from build_client_patch import (  # noqa: E402  (needs the sys.path line above)
    Dbc, EQ_CUSTOM_FAMILY, SF_ATTR0, SF_AURA, SF_BASEPOINTS, SF_CLASSMASK, SF_EFFECT,
    SF_FAMILY, SF_MISCA, SF_NAME,
)

# Spell is automatically cast on self by the core (SharedDefines.h:376). A talent
# chain whose rank spells are NOT passive grants an ability rather than a bonus.
SPELL_ATTR0_PASSIVE = 0x00000040

MANIFEST_PATH = os.path.join(MODULE_ROOT, "tools", "talent_manifest.json")
TALENT_SQL_PATH = os.path.join(MODULE_ROOT, "data/sql/db-world/06_talent_dbc.sql")

DB_CONTAINER = "ac-database"
DBC_CONTAINER = "ac-worldserver"
DBC_CONTAINER_PATH = "/azerothcore/env/dist/data/dbc/Spell.dbc"

ADD_FLAT_MODIFIER = 107
ADD_PCT_MODIFIER = 108

# Aura types that DO consult AuraEffect::IsAffectedOnSpell (Unit.cpp) and are
# therefore scoped by (family, classmask) exactly like a spellmod. Derived by
# grepping the call sites; refresh with:
#   grep -rn -B6 'IsAffectedOnSpell' src/server/game/Entities/Unit/Unit.cpp
AURA_FAMILY_GATED = frozenset({
    "SPELL_AURA_OVERRIDE_CLASS_SCRIPTS",
    "SPELL_AURA_MOD_DAMAGE_FROM_CASTER",
    "SPELL_AURA_MOD_ABILITY_IGNORE_TARGET_RESIST",
    "SPELL_AURA_MOD_TARGET_ABSORB_SCHOOL",
    "SPELL_AURA_MOD_TARGET_ABILITY_ABSORB_SCHOOL",
    "SPELL_AURA_MOD_HEALING_RECEIVED",
    "SPELL_AURA_MOD_ARMOR_PENETRATION_PCT",
    "SPELL_AURA_IGNORE_COMBAT_RESULT",
    "SPELL_AURA_ABILITY_IGNORE_AURASTATE",
})

# School-mask auras whose school comes from a MAX_SPELL_SCHOOL bit loop in the
# handler rather than a `ByMiscMask` helper, so the grep below cannot see them.
# AuraEffect::HandleModDamageDone / HandleModHealingDone (SpellAuraEffects.cpp).
AURA_SCHOOL_MASK_EXTRA = frozenset({
    "SPELL_AURA_MOD_DAMAGE_DONE",
    "SPELL_AURA_MOD_HEALING_DONE",
    "SPELL_AURA_MOD_HEALING_DONE_PERCENT",
    "SPELL_AURA_MOD_HEALING",
    "SPELL_AURA_MOD_DAMAGE_DONE_CREATURE",
})

# Auras that are a class mechanic by construction: C++ class-script hooks.
AURA_CLASS_SCRIPTED = frozenset({
    "SPELL_AURA_DUMMY",
    "SPELL_AURA_OVERRIDE_CLASS_SCRIPTS",
    "SPELL_AURA_ADD_TARGET_TRIGGER",
})

# Auras whose benefit is delivered by *another* spell (a proc, a periodic dummy,
# or a non-aura effect), so this row alone cannot say whether it crosses classes.
AURA_INDIRECT = frozenset({
    "SPELL_AURA_PROC_TRIGGER_SPELL",
    "SPELL_AURA_PROC_TRIGGER_SPELL_WITH_VALUE",
    "SPELL_AURA_PROC_TRIGGER_DAMAGE",
    "SPELL_AURA_PERIODIC_DUMMY",
    "SPELL_AURA_NONE",
})

# Live DB (mirrors tools/generate_spelldata.py) so this sees the shipped state,
# including the custom chains that never landed in the committed dump.
# ============================================================================
# Inputs
# ============================================================================

def run_query(query):
    """Run SQL against the live world DB, returning a list of dicts."""
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


def resolve_dbc(path):
    """Return a local Spell.dbc, copying it out of the worldserver if needed."""
    if path:
        return path

    local = os.path.join(REPO_ROOT, "env", "dist", "data", "dbc", "Spell.dbc")
    if os.path.exists(local):
        return local

    dest = os.path.join(MODULE_ROOT, "tools", "Spell.dbc")
    print(f"copying Spell.dbc from {DBC_CONTAINER} ...", file=sys.stderr)
    result = subprocess.run(
        ["docker", "cp", f"{DBC_CONTAINER}:{DBC_CONTAINER_PATH}", dest],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"could not copy Spell.dbc from {DBC_CONTAINER} ({result.stderr.strip()}).\n"
            "Pass --dbc PATH pointing at a Spell.dbc (server dbc/Spell.dbc or the "
            "output of tools/extract_client_dbcs.py)."
        )
    return dest


def parse_enum(path, prefixes):
    """name -> value for an enum in the core, so our labels can never drift."""
    values = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        match = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*,?\s*(?://.*)?$", line)
        if match and any(match.group(1).startswith(prefix) for prefix in prefixes):
            values.setdefault(int(match.group(2), 0), match.group(1))
    return values


def derive_school_mask_auras():
    """
    Aura types the engine consumes through a school/misc mask helper.

    These are school-wide *by construction*: the handler looks up the aura's
    EffectMiscValue as a school bitmask, so any class's spell of that school
    benefits. Derived by grepping the call sites rather than maintained by hand.
    """
    pattern = re.compile(r"Aura(?:Modifier|Multiplier)ByMiscMask\((SPELL_AURA_[A-Z0-9_]+)")
    found = set()
    for root, _, files in os.walk(CORE_ROOT):
        for name in files:
            if not name.endswith((".cpp", ".h")):
                continue
            text = open(os.path.join(root, name), encoding="utf-8", errors="replace").read()
            found.update(pattern.findall(text))
    return found


PET_TABS = frozenset({409, 410, 411})  # Hunter pet trees: deliberately unmapped


def describe_tab(tab_id, tab_classes):
    """(className, group) for the report; group 'class' means player-selectable."""
    if tab_id in tab_classes:
        return tab_classes[tab_id], "class"
    if tab_id in PET_TABS:
        return "Hunter-pet", "pet"
    if tab_id == 0:
        return "Custom-EQ", "custom"
    return f"tab-{tab_id}", "other"


def load_chains(talent_sql):
    """[(talentId, tabId, tierId, [rankSpellIds])] from the live DB or the dump."""
    if talent_sql:
        chains = []
        for match in re.finditer(r"^\(([0-9,]+)\)[,;]$", open(talent_sql, encoding="utf-8").read(), re.M):
            fields = [int(value) for value in match.group(1).split(",")]
            ranks = [value for value in fields[4:13] if value > 0]
            if ranks:
                chains.append((fields[0], fields[1], fields[2], ranks))
        return chains

    chains = []
    for row in run_query(
        "SELECT ID, TabID, TierID, SpellRank_1, SpellRank_2, SpellRank_3, SpellRank_4, "
        "SpellRank_5, SpellRank_6, SpellRank_7, SpellRank_8, SpellRank_9 FROM talent_dbc ORDER BY ID"
    ):
        ranks = [int(row[f"SpellRank_{i}"]) for i in range(1, 10) if int(row[f"SpellRank_{i}"]) > 0]
        if ranks:
            chains.append((int(row["ID"]), int(row["TabID"]), int(row["TierID"]), ranks))
    return chains


def load_spells(dbc_path, wanted):
    """{spellId: dbc row} for just the spells we care about (the file is ~50 MB)."""
    dbc = Dbc(dbc_path)
    rows = {}
    for index in range(dbc.recs):
        offset = index * dbc.recsize
        record_id = struct.unpack_from("<I", dbc.records, offset)[0]
        if record_id in wanted:
            rows[record_id] = struct.unpack_from(f"<{dbc.fields}i", dbc.records, offset)
    return dbc, rows


def dbc_string(dbc, offset):
    if offset <= 0:
        return ""
    return dbc.strings[offset:dbc.strings.index(0, offset)].decode("utf-8", "replace")


def classify_effect(row, eff_index, aura_names, school_mask_auras):
    """
    Verdict for one effect slot, per the engine rule in the module docstring.

    'spellmod-class-scoped' is the SpellClassMask trap: the benefit can only ever
    reach one class's spells.
    """
    aura = row[SF_AURA + eff_index]
    aura_name = aura_names.get(aura, f"aura#{aura}")
    family = row[SF_FAMILY]
    mask = tuple(row[SF_CLASSMASK + eff_index * 3 + j] for j in range(3))

    if aura in (ADD_FLAT_MODIFIER, ADD_PCT_MODIFIER):
        if not family:
            return "spellmod-global", aura_name, family, mask
        if family == EQ_CUSTOM_FAMILY:
            # Our own EQ pack family: those spells are class-agnostic, so the
            # scoping is to the pack rather than to a class.
            return "custom-family", aura_name, family, mask
        return "spellmod-class-scoped", aura_name, family, mask

    if aura_name in AURA_FAMILY_GATED:
        if family:
            return "class-scripted", aura_name, family, mask
        return "character-wide", aura_name, family, mask

    if aura_name in AURA_CLASS_SCRIPTED:
        return "class-scripted", aura_name, family, mask

    if aura_name in AURA_INDIRECT:
        return "indirect", aura_name, family, mask

    if aura_name in school_mask_auras or aura_name in AURA_SCHOOL_MASK_EXTRA:
        # A nonzero classmask is inert here: these auras are never routed
        # through IsAffectedOnSpell, so the school mask is the whole story.
        return "school-mask", aura_name, family, mask

    return "character-wide", aura_name, family, mask


# A talent is "needs-redesign" when any effect is class-scoped, "school-wide" when
# it has a class-agnostic benefit and no class-scoped one, and "class-mechanic"
# when its only effects are class-script hooks (correct by design - a Druid form
# bonus has no cross-class meaning).
CROSS_CLASS_VERDICTS = frozenset({"school-mask", "character-wide", "spellmod-global", "custom-family"})


# ============================================================================
# Classification
# ============================================================================

def classify_chains(chains, dbc, spells, aura_names, school_mask_auras, tab_classes):
    results = []
    for talent_id, tab_id, tier_id, ranks in chains:
        verdicts = collections.Counter()
        effects = []
        for spell_id in ranks:
            row = spells.get(spell_id)
            if not row:
                continue
            for eff_index in range(3):
                if row[SF_EFFECT + eff_index] == 0:
                    continue
                verdict, aura_name, family, mask = classify_effect(row, eff_index, aura_names, school_mask_auras)
                verdicts[verdict] += 1
                effects.append({
                    "spellId": spell_id,
                    "aura": aura_name,
                    "verdict": verdict,
                    "family": family,
                    "mask": list(mask),
                    "misc": row[SF_MISCA + eff_index],
                    "amount": row[SF_BASEPOINTS + eff_index] + 1,
                })

        rank_rows = [spells[spell_id] for spell_id in ranks if spell_id in spells]
        # A chain that grants an ability (Pyroblast, Conflagrate, Mutilate...) is
        # class-bound by nature: the second class gets nothing from it, but there
        # is nothing to "redesign" either, so it is its own bucket.
        grants_ability = bool(rank_rows) and not all(
            row[SF_ATTR0] & SPELL_ATTR0_PASSIVE for row in rank_rows
        )

        if grants_ability:
            label = "ability-grant"
        elif verdicts["spellmod-class-scoped"]:
            label = "needs-redesign"
        elif any(verdicts[verdict] for verdict in CROSS_CLASS_VERDICTS):
            label = "school-wide-aura"
        elif verdicts["indirect"]:
            label = "indirect"
        elif effects:
            label = "class-mechanic"
        else:
            label = "no-effect"

        results.append({
            "talentId": talent_id,
            "tabId": tab_id,
            "tierId": tier_id,
            "name": dbc_string(dbc, spells[ranks[0]][SF_NAME]) if ranks[0] in spells else "",
            "className": describe_tab(tab_id, tab_classes)[0],
            "group": describe_tab(tab_id, tab_classes)[1],
            "ranks": ranks,
            "label": label,
            "verdicts": dict(verdicts),
            "effects": effects,
        })
    return results


def report_summary(results, args, chain_source):
    lines = []
    add = lines.append
    total = len(results)
    labels = collections.Counter(r["label"] for r in results)

    add("# Talent synergy classification (Phase 1d)")
    add("")
    add(f"Generated by `tools/classify_talent_synergy.py` from {chain_source}.")
    add("")
    add("Every talent chain is classified by whether its benefit can cross classes -")
    add("whether a Fire Mage's talent does anything for a Destruction Warlock, or a Fury")
    add("Warrior's for a Feral Druid. The engine rule is quoted in the tool's docstring")
    add("(`SpellInfo::IsAffectedBySpellMod` -> `SpellInfo::IsAffected`).")
    add("")
    add("| label | meaning | count | share |")
    add("|---|---|---:|---:|")
    for label, meaning in (
        ("school-wide-aura", "class-agnostic benefit; pays off for both classes"),
        ("needs-redesign", "at least one benefit is locked to one spell family (the `SpellClassMask` trap)"),
        ("ability-grant", "grants an active ability; class-bound by nature, nothing to redesign"),
        ("class-mechanic", "class-script hook or class-only mechanic; no cross-class meaning"),
        ("indirect", "benefit comes from a triggered spell; needs a second pass"),
        ("no-effect", "no effects on any rank spell"),
    ):
        count = labels[label]
        add(f"| `{label}` | {meaning} | {count} | {count * 100 // max(total, 1)}% |")
    add(f"| **total** | | **{total}** | |")
    add("")

    add("## Per-class profile")
    add("")
    add("How much of each class's own tree benefits the *other* class of a pair. The rows")
    add("below the classes are not player-selectable: the Hunter pet trees (TabIDs")
    add("409-411, unmapped on purpose) and the custom EQ pack (TabID 0, draft-only).")
    add("")
    add("| group | talents | school-wide | needs-redesign | school-wide share |")
    add("|---|---:|---:|---:|---:|")
    by_class = collections.defaultdict(list)
    for result in results:
        by_class[result["className"]].append(result)
    ordered_groups = sorted(by_class, key=lambda c: (by_class[c][0]["group"] != "class",
                                                     -len(by_class[c]), c))
    for class_name in ordered_groups:
        group = by_class[class_name]
        school = sum(1 for r in group if r["label"] == "school-wide-aura")
        redesign = sum(1 for r in group if r["label"] == "needs-redesign")
        share = school * 100 // max(school + redesign, 1)
        add(f"| {class_name} | {len(group)} | {school} | {redesign} | {share}% |")
    add("")

    class_names = sorted({r["className"] for r in results if r["group"] == "class"})
    add("## Class pairings")
    add("")
    add("For each pair, the share of the two trees' union that pays off across both")
    add("classes. This is the number the design actually cares about: a low share means")
    add("the pairing mostly plays as two half-characters sharing a health bar.")
    add("")
    add("| pairing | union | pays off across both | share |")
    add("|---|---:|---:|---:|")
    pairs = []
    for index, first in enumerate(class_names):
        for second in class_names[index + 1:]:
            union = [r for r in results if r["className"] in (first, second)]
            school = sum(1 for r in union if r["label"] == "school-wide-aura")
            pairs.append((school * 100 // max(len(union), 1), first, second, len(union), school))
    for share, first, second, union_size, school in sorted(pairs, reverse=True)[:args.pairs]:
        add(f"| {first} + {second} | {union_size} | {school} | {share}% |")
    add("")

    unmapped = [r for r in results if r["group"] != "class"]
    if unmapped:
        add("## Non-player chains")
        add("")
        add("Chains in TabIDs absent from `tools/talent_manifest.json`, so listed for")
        add("completeness rather than as redesign targets.")
        add("")
        for tab_id in sorted({r["tabId"] for r in unmapped}):
            group = [r for r in unmapped if r["tabId"] == tab_id]
            add(f"- TabID {tab_id} ({group[0]['group']}): {len(group)} chains, e.g. "
                + ", ".join(sorted({r["name"] for r in group})[:4]))
        add("")
    return lines, add


def build_report(results, args, school_mask_auras, chain_source, family_names):
    lines, add = report_summary(results, args, chain_source)

    custom = [r for r in results if r["group"] == "custom"]
    if custom:
        spellmods = [r for r in custom
                     if any(e["verdict"] in ("spellmod-global", "spellmod-class-scoped", "custom-family")
                            for e in r["effects"])]
        inert = [r for r in spellmods
                 if any(e["verdict"] == "spellmod-global" and any(e["mask"]) for e in r["effects"])]
        add("## Custom EQ talent pack (TabID 0)")
        add("")
        add(f"{len(custom)} chains, all labelled `ability-grant` because their rank spells are")
        add("not marked `SPELL_ATTR0_PASSIVE` in the shipped `Spell.dbc` (`Attributes = 0`).")
        add("That is a defect, not a design choice, and it is the first of two found here.")
        add("")
        add("**Defect 1 - these talents never take effect.** A learned spell's auras are only")
        add("applied automatically when the spell is passive: `Player::_addSpell`")
        add("(Player.cpp:3139) and `Player::AddSpell` (Player.cpp:3334) both gate the")
        add("`CastSpell` on `spellInfo->IsPassive()`. No SQL file ships a `spell_dbc` row for")
        add("994001+ (`30_eq_talent_pack.sql` writes only `talent_dbc` and `spell_pet_auras`),")
        add("so the DBC row is the effective spell and the `ADD_*_MODIFIER` auras are never")
        add("applied. Fix: `row[SF_ATTR0] |= SPELL_ATTR0_PASSIVE` (`0x40`) in")
        add("`build_eq_talent_row`.")
        add("")
        if inert:
            add("**Defect 2 - the per-spell targeting is inert.** "
                f"{len(inert)} of the {len(spellmods)} spellmod talents carry")
            add("`EffectSpellClassMask` set but `SpellFamilyName = 0`, and")
            add("`SpellInfo::IsAffected` returns true on a zero family *before* it looks at the")
            add("mask. Even once defect 1 is fixed, each mod would apply to *every* spell the")
            add("character casts instead of the single EQ spell it was aimed at - while the")
            add(f"pack's own comment documents the intent as `SpellFamilyName = {EQ_CUSTOM_FAMILY}`")
            add("plus one classmask bit per target spell. Fix: `row[SF_FAMILY] = EQ_CUSTOM_FAMILY`")
            add("(keeping the bit in `SF_FAMILYFLAGS`), which also keeps the talent cross-class")
            add("because the EQ spells are themselves family 220.")
            add("")
        add("Both fixes change the shipped patch, so they need `build_client_patch.py` re-run")
        add("plus a new client patch and `dbc/Spell.dbc`; neither could be verified from here.")
        add("")
    redesign = [r for r in results if r["label"] == "needs-redesign"]
    add("## Needs-redesign talents")
    add("")
    add(f"{len(redesign)} chains whose benefit looks class-agnostic on the tooltip but is")
    add("delivered through `SpellFamilyName != 0`, so the second class gets nothing.")
    add("Fixing one means re-authoring the effect as a school-mask aura (e.g.")
    add("`SPELL_AURA_MOD_DAMAGE_PERCENT_DONE` with a fire misc value) or as a familyless")
    add("spellmod (`SpellFamilyName = 0`), whose classmask the engine then ignores.")
    add("")
    add("| class | talent | talent id | families | scoped effects |")
    add("|---|---|---:|---|---:|")
    ordered = sorted(redesign, key=lambda r: (r["className"], r["tierId"], r["name"]))
    for result in ordered[:args.limit]:
        families = sorted({e["family"] for e in result["effects"] if e["verdict"] == "spellmod-class-scoped"})
        add(f"| {result['className']} | {result['name']} | {result['talentId']} | "
            f"{families} | {result['verdicts'].get('spellmod-class-scoped', 0)} |")
    if len(redesign) > args.limit:
        add(f"| ... | _{len(redesign) - args.limit} more, see --json_ | | | |")
    add("")

    add("## Worked examples")
    add("")
    add("Sanity checks against talents whose behaviour is well known.")
    add("")
    add("| talent | label | effects |")
    add("|---|---|---|")
    for name in args.examples:
        for result in results:
            if result["name"].lower() != name.lower():
                continue
            detail = "; ".join(
                f"{e['aura'].replace('SPELL_AURA_', '')} family={e['family']} "
                f"misc={e['misc']} -> `{e['verdict']}`" for e in result["effects"][:3]
            )
            add(f"| {result['name']} | `{result['label']}` | {detail} |")
            break
    add("")
    add("## How the rule sets are derived")
    add("")
    add(f"- {len(school_mask_auras)} school-mask aura types, grepped from the core's "
        "`*ByMiscMask(SPELL_AURA_*)` call sites (plus the few handlers that loop over")
    add("  `MAX_SPELL_SCHOOL` on `EffectMiscValue`), so a `school-mask` verdict means the")
    add("  engine resolves the aura by school and cannot tell the classes apart.")
    add(f"- {len(AURA_FAMILY_GATED)} family-gated aura types, grepped from "
        "`IsAffectedOnSpell()` call sites.")
    add("- Spellmods (`ADD_FLAT_MODIFIER` / `ADD_PCT_MODIFIER`) are read straight from")
    add("  `SpellInfo::IsAffectedBySpellMod`, which is the code path the plan's")
    add("  \"SpellClassMask trap\" refers to.")
    add("")
    add("`family=N` below means `SpellFamilyName = N` (parsed from `SharedDefines.h`): "
        + ", ".join(f"{value}={name.replace('SPELLFAMILY_', '')}"
                    for value, name in sorted(family_names.items())) + ".")
    add("")
    return "\n".join(lines) + "\n"


# ============================================================================
# Entry point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dbc", help="Spell.dbc to read (default: copy it from the "
                                      "running worldserver container)")
    parser.add_argument("--talent-sql", help="read chains from this SQL dump instead of "
                                             "the live talent_dbc table")
    parser.add_argument("--out", help="write the markdown report here (default: stdout)")
    parser.add_argument("--json", dest="json_out", help="also write the raw classification")
    parser.add_argument("--limit", type=int, default=40,
                        help="rows to list per report table (default: 40)")
    parser.add_argument("--pairs", type=int, default=15,
                        help="class pairings to show (default: 15, best first)")
    parser.add_argument("--examples", nargs="*", default=[
        "Fire Power", "Improved Frostbolt", "Arcane Instability",
        "Elemental Precision", "Molten Core", "Improved Scorch",
    ], help="talents to show as worked examples")
    args = parser.parse_args()

    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8"))
    tab_classes = {tab["tabId"]: tab["class"].capitalize() for tab in manifest["tabs"]}

    chains = load_chains(args.talent_sql)
    chain_source = (f"the committed `{os.path.relpath(args.talent_sql, MODULE_ROOT)}`"
                    if args.talent_sql else "the live `talent_dbc` table")

    wanted = {spell_id for _, _, _, ranks in chains for spell_id in ranks}
    dbc, spells = load_spells(resolve_dbc(args.dbc), wanted)
    if len(spells) != len(wanted):
        print(f"note: {len(wanted) - len(spells)} rank spell(s) are not in Spell.dbc",
              file=sys.stderr)

    aura_names = parse_enum(os.path.join(CORE_ROOT, "game/Spells/Auras/SpellAuraDefines.h"),
                            ["SPELL_AURA_"])
    family_names = parse_enum(os.path.join(CORE_ROOT, "shared/SharedDefines.h"),
                              ["SPELLFAMILY_"])
    school_mask_auras = derive_school_mask_auras()

    results = classify_chains(chains, dbc, spells, aura_names, school_mask_auras, tab_classes)

    report = build_report(results, args, school_mask_auras, chain_source, family_names)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(report)
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(report)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(results, handle, indent=1, sort_keys=True)
            handle.write("\n")
        print(f"wrote {args.json_out}")

    labels = collections.Counter(result["label"] for result in results)
    print(" ".join(f"{name}={count}" for name, count in labels.most_common()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
