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
    SF_FAMILY, SF_FAMILYFLAGS, SF_MISCA, SF_NAME, SF_SCHOOL,
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
# needs-redesign breakdown (Phase 1d follow-up)
# ============================================================================
#
# Every chain labelled `needs-redesign` has at least one spellmod scoped by
# (SpellFamilyName, EffectSpellClassMask), so its benefit can never reach the
# character's other class. How hard that is to fix depends entirely on the
# SpellModOp it uses, which is the `EffectMiscValue` of the ADD_*_MODIFIER aura:
#
#   tier 1  a per-school aura lever EXISTS in this core -> swap the aura for it,
#           keeping the same school and magnitude. Mechanical.
#   tier 2  no per-school lever exists (cooldowns, cast times, duration, range,
#           radii, charges, ...) -> either drop SpellFamilyName (which makes the
#           mask inert, so the talent applies to EVERY spell) or leave it
#           class-locked. A balance decision, not a plumbing one.
#   tier 3  the op mutates a specific effect slot of a specific spell
#           (ALL_EFFECTS / EFFECT1-3 / *_MULTIPLIER) -> spell-specific by
#           construction; needs hand re-authoring.
#
# A chain is tier N when its WORST op is N, because one stubborn op blocks the
# whole chain.
SPELLMOD_LEVERS = {
    0:  ("1", "SPELL_AURA_MOD_DAMAGE_PERCENT_DONE"),
    22: ("1", "SPELL_AURA_MOD_DAMAGE_PERCENT_DONE"),
    7:  ("1", "SPELL_AURA_MOD_SPELL_CRIT_CHANCE_SCHOOL"),
    15: ("1", "SPELL_AURA_MOD_CRIT_DAMAGE_BONUS"),
    16: ("1", "SPELL_AURA_MOD_INCREASES_SPELL_PCT_TO_HIT"),
    14: ("1", "SPELL_AURA_MOD_POWER_COST_SCHOOL_PCT"),
    2:  ("1", "SPELL_AURA_MOD_THREAT"),
    28: ("1", "SPELL_AURA_MOD_DISPEL_RESIST"),
    10: ("2", None), 11: ("2", None), 1: ("2", None), 5: ("2", None),
    6: ("2", None), 4: ("2", None), 21: ("2", None), 9: ("2", None),
    17: ("2", None), 19: ("2", None), 26: ("2", None), 30: ("2", None),
    3: ("3", None), 8: ("3", None), 12: ("3", None), 23: ("3", None),
    13: ("3", None), 18: ("3", None), 20: ("3", None), 24: ("3", None),
    27: ("3", None), 28: ("3", None),
}

SPELLMOD_OP_NAMES = {
    0: "DAMAGE", 1: "DURATION", 2: "THREAT", 3: "EFFECT1", 4: "CHARGES",
    5: "RANGE", 6: "RADIUS", 7: "CRIT_CHANCE", 8: "ALL_EFFECTS",
    9: "NOT_LOSE_CASTING", 10: "CAST_TIME", 11: "COOLDOWN", 12: "EFFECT2",
    13: "IGNORE_ARMOR", 14: "COST", 15: "CRIT_DAMAGE", 16: "RESIST_MISS",
    17: "JUMP_TARGETS", 18: "CHANCE_OF_SUCCESS", 19: "ACTIVATION_TIME",
    20: "DAMAGE_MULTIPLIER", 21: "GLOBAL_COOLDOWN", 22: "DOT",
    23: "EFFECT3", 24: "BONUS_MULTIPLIER", 26: "PROC_PER_MINUTE",
    27: "VALUE_MULTIPLIER", 28: "RESIST_DISPEL_CHANCE", 30: "COST_REFUND",
}

SCHOOL_MASKS = {1: "Physical", 2: "Holy", 4: "Fire", 8: "Nature",
                16: "Frost", 32: "Shadow", 64: "Arcane"}

# Effects/auras that make a spell a heal or a damaging spell. Used to tell the
# damage-side talents from the healing-side ones: DAMAGE/DOT spellmods served
# Blizzard for BOTH (the same lever carries +healing%), and the school-mask
# replacement differs (MOD_DAMAGE_PERCENT_DONE vs MOD_HEALING_DONE_PERCENT).
# Values are this core's SpellEffects/AuraType enums (SharedDefines.h /
# SpellAuraDefines.h) - note HEAL_MAX_HEALTH is 67 here and HEAL_MECHANICAL 75,
# not the 23/56 some other cores use.
HEAL_EFFECTS = frozenset({9, 10, 67, 75, 136})  # LEECH, HEAL, HEAL_MAX_HEALTH, HEAL_MECHANICAL, HEAL_PCT
HEAL_AURAS = frozenset({8})                     # PERIODIC_HEAL
DAMAGE_EFFECTS = frozenset({2, 17, 31, 58, 121})  # SCHOOL_DAMAGE + the four weapon-damage effects
DAMAGE_AURAS = frozenset({3, 89})                 # PERIODIC_DAMAGE, PERIODIC_DAMAGE_PERCENT


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


def build_family_index(dbc):
    """
    {SpellFamilyName: [(familyFlags0, flags1, flags2, school, e0..e2, a0..a2,
                        nameOffset, spellId)]}.

    Needed to expand an EffectSpellClassMask into the spells it governs, which is
    exactly what `SpellInfo::IsAffected` does: same SpellFamilyName, and any
    overlapping bit between the mod's mask and the spell's SpellFamilyFlags.
    Stored compactly - the DBC has ~50k rows. The last two fields are appended for
    callers that need to identify a spell (school derivation matches spell names
    against a talent's tooltip); everything before them keeps its index, so
    existing consumers are unaffected.
    """
    index = collections.defaultdict(list)
    effects = [SF_EFFECT, SF_EFFECT + 1, SF_EFFECT + 2]
    auras = [SF_AURA, SF_AURA + 1, SF_AURA + 2]
    for offset in range(0, dbc.recs * dbc.recsize, dbc.recsize):
        row = struct.unpack_from(f"<{dbc.fields}i", dbc.records, offset)
        index[row[SF_FAMILY]].append(
            (row[SF_FAMILYFLAGS], row[SF_FAMILYFLAGS + 1], row[SF_FAMILYFLAGS + 2],
             row[SF_SCHOOL]) + tuple(row[f] for f in effects) + tuple(row[f] for f in auras)
            + (row[SF_NAME], row[0])
        )
    return index


def expand_mask(index, family, mask):
    """The spells a class-scoped spellmod reaches."""
    return [entry for entry in index.get(family, ())
            if any(mask[j] and (entry[j] & mask[j]) for j in range(3))]


def analyze_breakdown(results, index):
    """Group the needs-redesign chains into tiers, with healing flagged."""
    everything = {0, 1, 2}
    rows = []
    for result in results:
        if result["label"] != "needs-redesign":
            continue
        scoped = [e for e in result["effects"] if e["verdict"] == "spellmod-class-scoped"]
        ops = sorted({e["misc"] for e in scoped})
        tiers = {SPELLMOD_LEVERS.get(op, ("3", None))[0] for op in ops}
        healed = False
        damaged = False
        touched = 0
        for effect in scoped:
            affected = expand_mask(index, effect["family"], effect["mask"])
            touched = max(touched, len(affected))
            for entry in affected:
                for i in everything:
                    healed = healed or entry[4 + i] in HEAL_EFFECTS or entry[7 + i] in HEAL_AURAS
                    damaged = damaged or entry[4 + i] in DAMAGE_EFFECTS or entry[7 + i] in DAMAGE_AURAS
        # `healed` alone is not "this is a healing talent": Death Strike both
        # damages and heals, so its talent is a hybrid needing both auras.
        side = "hybrid" if (healed and damaged) else ("heal-only" if healed else "damage")
        rows.append({
            "className": result["className"],
            "name": result["name"],
            "talentId": result["talentId"],
            "ops": ops,
            "tier": max(tiers),
            "mixed": len(tiers) > 1,
            "healed": healed,
            "side": side,
            "touched": touched,
            "improved": result["name"].startswith("Improved "),
        })
    return rows


# ============================================================================
# needs-redesign breakdown report
# ============================================================================

def breakdown_head(rows, overrides=0):
    """Markdown: the needs-redesign work split by what the fix requires."""
    lines = []
    add = lines.append
    total = len(rows)
    by_tier = collections.Counter(r["tier"] for r in rows)
    tier1 = [r for r in rows if r["tier"] == "1"]
    mixed = sum(1 for r in rows if r["mixed"])
    improved = sum(1 for r in rows if r["improved"])

    add("# needs-redesign breakdown (Phase 1d follow-up)")
    add("")
    if overrides:
        add(f"Generated with the live `spell_dbc` overrides applied ({overrides} rows), so the")
        add("chains already broadened by `tools/broaden_talent_scoping.py` are no longer listed")
        add("here. Drop `--apply-spell-dbc` for the stock-Spell.dbc view.")
        add("")
    add(f"The {total} chains labelled `needs-redesign` by `tools/classify_talent_synergy.py`,")
    add("split by what the fix actually requires. A chain's tier is the **worst** op it uses,")
    add("because one stubborn op blocks the whole chain.")
    add("")
    add("| tier | what it means | chains | effort |")
    add("|---|---|---:|---|")
    add(f"| **1** | every scoped op has a per-school aura lever | {by_tier['1']} | swap the aura |")
    add(f"| **2** | an op has no per-school lever | {by_tier['2']} | a balance decision |")
    add(f"| **3** | an op targets one effect slot | {by_tier['3']} | hand re-author |")
    add("")
    add("Tier 1's ops are the damage/healing, crit, cost, threat and resist ones, and this")
    add("core has a school-mask aura for each (listed below). Tier 2's are the timers and")
    add("ranges - cooldown, cast time, duration, range, radius, charges - where no")
    add("per-school lever exists. Tier 3's are `ALL_EFFECTS` / `EFFECT1-3` / `*_MULTIPLIER`,")
    add("which scale a specific effect slot and are therefore spell-specific by construction.")
    add("")
    add(f"Mixed chains (ops from more than one tier, so more than one fix): {mixed}.")
    add("")

    add("## Tier 1 - the mechanical bucket")
    add("")
    if tier1:
        add("Each op maps to an aura this core already consumes per school:")
    else:
        add("**Empty: this bucket is done.** Every chain whose ops all have a school-mask")
        add("lever is converted in `data/sql/db-world/34_school_scope_tier1.sql`, so nothing")
        add("is listed here. The lever table stays as the reference for what each op maps to.")
    add("")
    add("| SpellModOp | per-school aura lever |")
    add("|---|---|")
    for op in sorted(SPELLMOD_LEVERS):
        tier, lever = SPELLMOD_LEVERS[op]
        if tier == "1":
            add(f"| `SPELLMOD_{SPELLMOD_OP_NAMES.get(op, op)}` | `{lever}` |")
    add("")
    add("Three things the conversions had to settle, all checked against this core rather")
    add("than assumed:")
    add("")
    add("- **`DAMAGE`/`DOT` split by intent.** The same lever carried Blizzard's +healing%")
    add("  talents, so a talent that boosts healing needs `MOD_HEALING_DONE_PERCENT`")
    add("  (which takes no school), and a \"damage *and* healing\" talent needs both auras.")
    add("  The side comes from the **tooltip**, not the classmask: the mask only has to")
    add("  *touch* a healing spell to look hybrid (`\"the damage of Blood Strike\"` looks")
    add("  hybrid because Death Strike heals itself), which flagged ~20 talents wrongly.")
    add("- **Magnitudes transfer 1:1, including `DAMAGE`.** `SpellDamageBonusDone` folds the")
    add("  school-mask auras into `DoneTotalMod = SpellPctDamageModsDone(...)` (Unit.cpp:8496),")
    add("  forms `tmpDamage = (pdamage + DoneTotal) * DoneTotalMod` (8634), and *then* runs")
    add("  `ApplySpellMod(SPELLMOD_DAMAGE, tmpDamage)` (8637). The spellmod multiplies the")
    add("  same total the aura multiplies, so moving it into the aura is 1:1 - no re-tuning.")
    add("- **`THREAT` is 1:1 only in its pct form.** The pct spellmod is")
    add("  `threat * (1 + value/100)` and `MOD_THREAT` is `threat * (100 + amount)/100`; both")
    add("  are percentages, and Blizzard's own Silent Resolve carries the same `-7` as both")
    add("  an aura and a spellmod. The flat form is centi-threat (`ApplySpellMod` divides it")
    add("  by 100) and has no percentage equivalent, so it is reported as a skip.")
    add("")
    if not tier1:
        return lines, add, tier1, improved
    add("### Effort by class")
    add("")
    add("| class | tier 1 | broad (not \"Improved ...\") | damage-side | heal-only | hybrid |")
    add("|---|---:|---:|---:|---:|---:|")
    for class_name in sorted({r["className"] for r in tier1}):
        group = [r for r in tier1 if r["className"] == class_name]
        broad = sum(1 for r in group if not r["improved"])
        sides = collections.Counter(r["side"] for r in group)
        add(f"| {class_name} | {len(group)} | {broad} | {sides['damage']} | "
            f"{sides['heal-only']} | {sides['hybrid']} |")
    add("")
    return lines, add, tier1, improved


def render_breakdown(rows, overrides=0):
    """The full breakdown document."""
    lines, add, tier1, improved = breakdown_head(rows, overrides)
    add("## Tier 2 - no lever exists")
    add("")
    add("The engine has no per-school aura for these, so each is a policy call:")
    add("")
    add("- **Drop `SpellFamilyName`** - the mask becomes inert, so the talent applies to")
    add("  *every* spell the character casts. Keeps the fantasy (\"your spells are cheaper /")
    add("  faster\") but is a uniform increase across both classes.")
    add("- **Leave it class-locked** and document it. Nothing breaks; the pairing just gets")
    add("  less out of that tree.")
    add("")
    for tier, heading in (("2", "### Tier 2 ops"), ("3", "## Tier 3 - spell-specific by construction")):
        if tier == "3":
            add(heading)
            add("")
            add("These mutate one effect slot of one spell, so there is no generic substitute:")
            add("the talent has to be re-authored around a different effect (or left alone).")
            add("")
        else:
            add(heading)
            add("")
        ops = collections.Counter()
        for row in rows:
            if row["tier"] == tier:
                for op in row["ops"]:
                    if SPELLMOD_LEVERS.get(op, ("3", None))[0] == tier:
                        ops[SPELLMOD_OP_NAMES.get(op, op)] += 1
        add("| `SpellModOp` | chains |")
        add("|---|---:|")
        for name, count in ops.most_common():
            add(f"| `SPELLMOD_{name}` | {count} |")
        add("")

    add("## Why the school cannot be picked mechanically")
    add("")
    add("The obvious shortcut - derive the replacement's school from the spells the mask")
    add("governs - does not work, for two measured reasons:")
    add("")
    touched = sorted(r["touched"] for r in rows)
    add(f"- The masks are **coarse**: expanding them gives a median of {touched[len(touched) // 2]}")
    add(f"  spells per chain across the whole needs-redesign set (max {touched[-1]}), whose schools")
    add("  union to things like `Physical+Fire+Nature+Frost+Shadow`. The bits are shared with")
    add("  cosmetic, test and NPC spells, so a damage-only talent looks pan-school.")
    add("- The talent's own spell carries `SchoolMask = Physical` for almost every chain,")
    add("  so it is no hint either.")
    add("")
    add("The school therefore has to be read off each talent's name/tooltip: one judgement")
    add("call per converted talent. That, not the plumbing, is the real cost of tier 1.")
    add("")

    add("## Shipping")
    add("")
    add("The aura lives in `Spell.dbc`, but the world DB's `spell_dbc` override table carries")
    add("`EffectAura_1..3`, `EffectMiscValue_*`, `EffectSpellClassMaskA/B/C_*`, `SpellClassSet`")
    add("and `Attributes`. A conversion can ship **server-side as SQL** and be hot-swapped;")
    add("only the client tooltip needs the client patch (`patch-P.mpq` + `dbc/Spell.dbc`) to")
    add("stop lying. Both go through `tools/build_client_patch.py`.")
    add("")

    recommended = [r for r in rows if r["tier"] == "1" and not r["improved"]
                   and r["side"] == "damage"]
    add("## Suggested first cut")
    add("")
    add(f"Tier 1, broad (not `Improved <spell>`), damage-side: **{len(recommended)} chains**, spread")
    add("evenly across the classes. Their tooltips already promise a school-wide-style benefit, so")
    add("converting them needs no renaming and no healing/damage judgement - only the school and a")
    add("magnitude re-tune.")
    add("")
    add("| class | chains |")
    add("|---|---:|")
    for class_name, count in collections.Counter(r["className"] for r in recommended).most_common():
        add(f"| {class_name} | {count} |")
    add("")
    add("Deliberately excluded:")
    add("")
    t1_improved = sum(1 for r in tier1 if r["improved"])
    t1_other = sum(1 for r in tier1 if r["side"] != "damage")
    add(f"- the {t1_improved} `Improved <spell>` chains inside tier 1 ({improved} across the whole")
    add("  needs-redesign set) - spell-specific by name *and* intent (\"Improved Fireball\" is")
    add("  about Fireball), so converting them means renaming them.")
    add(f"- the {t1_other} tier-1 chains whose masks touch a healing spell, which need the healing")
    add("  aura (and both auras when they are hybrids).")
    add("")
    add("## Full tier-1 list")
    add("")
    add("| class | talent | id | ops | lever | spells touched | side |")
    add("|---|---|---:|---|---|---:|---|")
    for row in sorted(tier1, key=lambda r: (r["className"], r["name"])):
        levers = sorted({SPELLMOD_LEVERS[op][1] for op in row["ops"]
                         if SPELLMOD_LEVERS.get(op, ("3", None))[0] == "1"})
        names = ", ".join(f"`{SPELLMOD_OP_NAMES.get(op, op)}`" for op in row["ops"])
        add(f"| {row['className']} | {row['name']} | {row['talentId']} | {names} | "
            f"{', '.join('`' + l + '`' for l in levers)} | {row['touched']} | {row['side']} |")
    add("")
    return "\n".join(lines) + "\n"


def load_spell_overrides(dbc, spells):
    """
    Replace the loaded DBC rows with the live `spell_dbc` overrides.

    The core loads Spell.dbc and then lets spell_dbc replace rows wholesale
    (DBCStore -> DBCDatabaseLoader walks the DBC format string and reads
    `SELECT * ... ORDER BY ID DESC` positionally), so this mirrors that: columns
    map to DBC field indices 1:1. Text columns are left as the DBC value because
    the loader treats an empty string as "not overridden", and float columns are
    packed back to their raw bit pattern.
    """
    columns = run_query(
        "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = 'acore_world' AND TABLE_NAME = 'spell_dbc' ORDER BY ORDINAL_POSITION"
    )
    types = [row["DATA_TYPE"] for row in columns]
    applied = 0
    for row in run_query("SELECT * FROM spell_dbc"):
        spell_id = int(row["ID"])
        if spell_id not in spells:
            continue
        base = spells[spell_id]
        merged = list(base)
        for index, data_type in enumerate(types):
            name = columns[index]["COLUMN_NAME"]
            value = row.get(name)
            if data_type in ("varchar", "char", "text") or value in (None, ""):
                continue
            if data_type == "float":
                merged[index] = struct.unpack("<i", struct.pack("<f", float(value)))[0]
            else:
                merged[index] = int(value)
        spells[spell_id] = merged
        applied += 1
    return applied


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
    parser.add_argument("--breakdown", action="store_true",
                        help="report the needs-redesign chains split by fix tier instead "
                             "of the synergy classification")
    parser.add_argument("--apply-spell-dbc", action="store_true",
                        help="overlay the live `spell_dbc` overrides onto Spell.dbc first, "
                             "so the classification reflects what the server actually loads")
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
    overrides = 0
    if args.apply_spell_dbc:
        overrides = load_spell_overrides(dbc, spells)
        print(f"applied {overrides} spell_dbc override(s)", file=sys.stderr)
    if len(spells) != len(wanted):
        print(f"note: {len(wanted) - len(spells)} rank spell(s) are not in Spell.dbc",
              file=sys.stderr)

    aura_names = parse_enum(os.path.join(CORE_ROOT, "game/Spells/Auras/SpellAuraDefines.h"),
                            ["SPELL_AURA_"])
    family_names = parse_enum(os.path.join(CORE_ROOT, "shared/SharedDefines.h"),
                              ["SPELLFAMILY_"])
    school_mask_auras = derive_school_mask_auras()

    results = classify_chains(chains, dbc, spells, aura_names, school_mask_auras, tab_classes)

    if args.breakdown:
        report = render_breakdown(analyze_breakdown(results, build_family_index(dbc)), overrides)
    else:
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
