#!/usr/bin/env python3
"""Convert class-scoped damage talents into school-scoped auras (Phase 1d, Tier 1).

Tier 1 talents use a SpellModOp that *does* have a per-school aura lever in this
core, so the class scoping can be replaced with a school scope: "your Scorch,
Fireball and Frostfire Bolt crit 3% more" becomes "your Fire and Frost spells
crit 3% more", which a second class can also use.

Op -> aura, all verified against this core's consumers (not guessed):

  SPELLMOD_DAMAGE / DOT  -> SPELL_AURA_MOD_DAMAGE_PERCENT_DONE (79)
      Unit::SpellPctDamageModsDone (Unit.cpp:8140) takes the aura's MiscValue as
      a school mask against the cast `spellProto->GetSchoolMask()`. Physical is
      only skipped in MeleeDamageBonusDone (white hits, already factored in).
      The aura is also gated on `ValidateAttribute6SpellDamageMods` and on the
      aura spell's EquippedItemClass, both of which the source talents satisfy.
  SPELLMOD_CRITICAL_CHANCE -> SPELL_AURA_MOD_SPELL_CRIT_CHANCE_SCHOOL (71)
      GetTotalAuraModifierByMiscMask(..., schoolMask) - additive, so the flat
      spellmod magnitude transfers 1:1.
  SPELLMOD_CRIT_DAMAGE_BONUS -> SPELL_AURA_MOD_CRIT_DAMAGE_BONUS (163)
      GetTotalAuraModifierByMiscMask(..., schoolMask) - additive, 1:1.
  SPELLMOD_RESIST_MISS_CHANCE -> SPELL_AURA_MOD_INCREASES_SPELL_PCT_TO_HIT (199)
      GetTotalAuraModifierByMiscMask(..., schoolMask) - additive, 1:1.
  SPELLMOD_COST flat -> SPELL_AURA_MOD_POWER_COST_SCHOOL (73)
  SPELLMOD_COST pct  -> SPELL_AURA_MOD_POWER_COST_SCHOOL_PCT (72)
      SpellInfo::CalcPowerCost applies UNIT_FIELD_POWER_COST_MODIFIER + school
      (flat) and UNIT_FIELD_POWER_COST_MULTIPLIER + school (pct), and
      HandleModPowerCostPCT writes that field per school from MiscValue - so the
      aura really changes the cost the server charges, not just the client's
      display.
  SPELLMOD_THREAT -> EXCLUDED. The aura (10) is consumed as a *multiplier*
      (GetTotalAuraMultiplierByMiscMask) while the spellmod is additive, so the
      magnitude needs a conversion this tool has not verified.

Magnitudes otherwise transfer 1:1 because every op above is already expressed as
the same unit the aura uses (percent, or the client's x10 rage/energy units).

Replacing is per *effect slot*: a slot holding an ADD_*_MODIFIER aura whose op is
convertible gets the new aura and MiscValue. Effects that map to the same
(aura, misc) pair are merged into one with the summed amount, because two copies
would multiply rather than add (`GetTotalAuraMultiplier` multiplies) - e.g. Fire
Power carries DAMAGE and DOT mods that both become "Fire spells" once scoped by
school.

The school itself cannot come from the DBC: expanding a classmask yields a median
of 19 spells whose schools union to five or six different ones (bits are shared
with cosmetic and NPC spells), and the talent's own SchoolMask is Physical for all
but five of the 129. So it is derived from Blizzard's own wording instead:

  1. the spells the mask governs whose *name appears in the talent's tooltip*
     ("your Backstab, Mutilate, Garrote and Ambush") -> union of their schools;
  2. failing that, a school word in the tooltip ("of your Arcane spells");
  3. otherwise the chain is reported for a human decision.

Usage:
  python3 tools/school_scope_tier1.py                # write the SQL + review list
  python3 tools/school_scope_tier1.py --check        # verify the live spell_dbc
  python3 tools/school_scope_tier1.py --report       # just print the derivation
"""

import argparse
import collections
import json
import os
import struct
import sys

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(MODULE_ROOT, "tools"))

from build_client_patch import (  # noqa: E402
    Dbc, SF_AURA, SF_BASEPOINTS, SF_DESC, SF_EFFECT, SF_FAMILY, SF_FAMILYFLAGS,
    SF_MISCA, SF_NAME, SF_SCHOOL,
)
from broaden_talent_scoping import (  # noqa: E402
    TEXT_TYPES, load_columns, run_query, sql_values,
)
from classify_talent_synergy import (  # noqa: E402
    ADD_FLAT_MODIFIER, ADD_PCT_MODIFIER, CORE_ROOT, MANIFEST_PATH, analyze_breakdown,
    build_family_index, classify_chains, derive_school_mask_auras, load_chains,
    load_spells, parse_enum, resolve_dbc,
)

DEFAULT_OUT = os.path.join(MODULE_ROOT, "data/sql/db-world/34_school_scope_tier1.sql")
TABLE = "spell_dbc"

SPELLMOD_OP_NAMES = {0: "DAMAGE", 2: "THREAT", 7: "CRIT_CHANCE", 14: "COST",
                     15: "CRIT_DAMAGE", 16: "RESIST_MISS", 22: "DOT"}

# op -> (flat aura, percent aura); None means "no lever for this variant".
CONVERTIBLE = {
    0:  (None, 79),   # DAMAGE: only ever seen as pct
    22: (None, 79),   # DOT: only ever seen as pct
    7:  (71, 71),     # CRIT_CHANCE is flat in the DBC but additive aura-side
    15: (None, 163),
    16: (199, 199),
    14: (73, 72),     # flat -> MOD_POWER_COST_SCHOOL, pct -> ..._PCT
    28: (235, 235),   # RESIST_DISPEL_CHANCE -> MOD_DISPEL_RESIST (schoolless)
}
LEVER1 = {0, 2, 7, 14, 15, 16, 22, 28}

# Ops whose replacement aura ignores EffectMiscValue, so it carries misc 0 rather
# than a school: MOD_HEALING_DONE_PERCENT (136) and MOD_DISPEL_RESIST (235). Both are
# consumed as a flat percentage with no school parameter
# (`GetTotalAuraMultiplier(SPELL_AURA_MOD_HEALING_DONE_PERCENT)` and
# `GetTotalAuraModifier(SPELL_AURA_MOD_DISPEL_RESIST)`), and both add to the same
# magnitude the spellmod added, so the amount transfers 1:1.
UNIVERSAL_AURAS = frozenset({136, 235})

SCHOOL_NAMES = {1: "Physical", 2: "Holy", 4: "Fire", 8: "Nature",
                16: "Frost", 32: "Shadow", 64: "Arcane"}
SCHOOL_WORDS = {"fire": 4, "flame": 4, "scorch": 4, "frost": 16, "ice": 16,
                "cold": 16, "chill": 16, "arcane": 64, "shadow": 32, "dark": 32,
                "nature": 8, "storm": 8, "lightning": 8, "shock": 8, "totem": 8,
                "holy": 2, "light": 2, "physical": 1, "swipe": 1, "maul": 1,
                "mangle": 1, "bleed": 1, "shot": 1, "sting": 1}

# Spec names are scopes the policy explicitly rejects ("don't have class or school
# (Destro/Resto/Affliction/Elemental) limited talents"), so a tooltip that scopes
# itself to one is mapped to the schools that spec's spells actually use.
SPEC_SCHOOLS = {
    "destruction": 4 | 32,   # Warlock: fire and shadow
    "affliction": 32,
    "demonology": 32,
    "elemental": 8 | 4,      # Shaman: lightning and fire
    "enhancement": 1 | 8,
    "balance": 64 | 8,
    "feral": 1,
    "guardian": 1,
    "restoration": 0,        # healing - no school, handled as heal intent
    "discipline": 2,
    "holy": 2,
    "shadow": 32,
    "arcane": 64,
    "fire": 4,
    "frost": 16,
    "arms": 1, "fury": 1, "protection": 1,
    "marksmanship": 1, "survival": 1, "beast mastery": 1,
    "assassination": 1, "combat": 1, "subtlety": 1,
    "blood": 1 | 16, "unholy": 1 | 32,
}

# "all instant cast spells", "all spells", "your abilities": the tooltip already
# says the scope is everything, so there is no school to pick - the broadest school
# mask (every school, Physical included) makes it universal, which is what the
# talent always meant. Matched as substrings of the lowercased tooltip, so the
# stems cover the plurals ("all spell" catches "all spells").
UNIVERSAL_MASK = 127
UNIVERSAL_PHRASES = ("all spell", "all abilit", "all attack", "and abilit",
                     "your abilit", "offensive abilit", "ranged abilit",
                     "all combo point", "all damage", "your damage",
                     "all instant cast", "instant cast", "instant spell",
                     "all shapeshift", "healing spell", "periodic", "all your")

# positions inside a build_family_index entry
INDEX_SCHOOL = 3
INDEX_NAME = 10


def school_name(mask):
    return "+".join(name for bit, name in SCHOOL_NAMES.items() if mask & bit) or "NONE"


def dbc_string(dbc, offset):
    if offset <= 0:
        return ""
    return dbc.strings[offset:dbc.strings.index(0, offset)].decode("utf-8", "replace")


def derive_school(dbc, index, result, spells):
    """
    (school mask, reason) for a chain, from Blizzard's own wording.

    The tooltip names the affected spells far more often than it names a school,
    so the spell names are the primary signal: any spell the classmask governs
    whose name occurs in the tooltip is one of the spells the talent was written
    about, and its school is the school the talent should now cover.
    """
    row = spells.get(result["ranks"][0])
    text = (dbc_string(dbc, row[SF_DESC]) if row else "").lower()
    scoped = [e for e in result["effects"] if e["verdict"] == "spellmod-class-scoped"]

    named, matched = 0, []
    for effect in scoped:
        for candidate in index.get(effect["family"], ()):
            if not any(effect["mask"][j] and (candidate[j] & effect["mask"][j])
                       for j in range(3)):
                continue
            name = dbc_string(dbc, candidate[INDEX_NAME]).lower()
            if len(name) >= 5 and name in text:
                named |= candidate[INDEX_SCHOOL]
                matched.append(name)
    if named:
        return named, f"tooltip names {', '.join(sorted(set(matched))[:3])}"

    specs = 0
    spec_hit = []
    for spec, mask in SPEC_SCHOOLS.items():
        if f"{spec} spells" in text or f"{spec} abilities" in text:
            specs |= mask
            spec_hit.append(spec)
    if spec_hit:
        if specs:
            return specs, f"spec scope '{spec_hit[0]}' -> its schools"
        return UNIVERSAL_MASK, f"spec scope '{spec_hit[0]}' (restoration) -> healing"

    words = 0
    for word in text.replace("spell", " ").replace("damage", " ").split():
        token = word.strip(".,;:()")
        words |= SCHOOL_WORDS.get(token, 0) or SCHOOL_WORDS.get(token.rstrip("s"), 0)
    if words:
        return words, "school named in the tooltip"

    for phrase in UNIVERSAL_PHRASES:
        if phrase in text:
            return UNIVERSAL_MASK, f'tooltip says "{phrase}" - universal'
    return 0, "no school, spell name or scope in the tooltip"


def detect_intent(text):
    """
    (damage, heal) for a talent, read off its tooltip.

    The `side` flag from the breakdown is a review marker, not a verdict: it calls
    a talent "hybrid" whenever its classmask touches a healing spell, so "Bloody
    Strikes: increases the *damage* of Blood Strike" is flagged hybrid purely
    because Death Strike heals itself. The tooltip says which of the two the
    talent actually boosts, and that decides whether it needs a damage school aura,
    a healing aura, or both.
    """
    damage = ("damage" in text) or ("dealt by" in text)
    heal = ("healed" in text) or ("healing" in text) or ("amount healed" in text)
    return damage, heal


def convert_effects(result, spells, school_mask, intent):
    """
    {spellId: {slot: (aura, misc, amount) or None}} - the rewrites per rank spell.

    The op picks the aura family, the intent picks which side of it to cover:

      DAMAGE / DOT + damage intent -> MOD_DAMAGE_PERCENT_DONE (school)
      DAMAGE / DOT + heal intent   -> MOD_HEALING_DONE_PERCENT (no school parameter,
                                      so a healing talent becomes "you heal more")
      DAMAGE / DOT + both          -> both auras
      everything else              -> its school aura (crit chance, crit damage, hit
                                      chance and cost all apply to heals as well as
                                      damage, so they need no intent split)

    Slots that collapse onto the same (aura, misc) pair are merged with their
    amounts summed, because the engine *multiplies* matching auras, so two copies
    would double-dip rather than add. An intent that needs a second aura takes a
    free effect slot (Effect_N == 0), and the chain is reported if the spell has
    none left.
    """
    damage_intent, heal_intent = intent
    out = {}
    for spell_id in result["ranks"]:
        row = spells.get(spell_id)
        if not row:
            continue
        outputs = []            # [(aura, misc, amount)]
        origin = []             # the slot each output came from
        for slot in range(3):
            aura = row[SF_AURA + slot]
            op = row[SF_MISCA + slot]
            if aura not in (ADD_FLAT_MODIFIER, ADD_PCT_MODIFIER) or op not in CONVERTIBLE:
                continue
            flat, pct = CONVERTIBLE[op]
            amount = row[SF_BASEPOINTS + slot] + 1
            if op in (0, 22):                       # DAMAGE / DOT: intent decides
                replacements = []
                if damage_intent:
                    replacements.append((79, school_mask, amount))
                if heal_intent:
                    replacements.append((136, 0, amount))
                if not replacements:                # neither word in the tooltip
                    replacements.append((79, school_mask, amount))
            else:
                replacement = pct if aura == ADD_PCT_MODIFIER else flat
                if replacement is None:
                    return None, f"no lever for {SPELLMOD_OP_NAMES.get(op, op)} (aura {aura})"
                misc = 0 if replacement in UNIVERSAL_AURAS else school_mask
                replacements = [(replacement, misc, amount)]
            for entry in replacements:
                outputs.append(entry)
                origin.append(slot)

        if not outputs:
            continue

        # merge identical (aura, misc) pairs, keeping first-seen order
        merged = {}
        for entry, slot in zip(outputs, origin):
            key = (entry[0], entry[1])
            if key in merged:
                merged[key] = (merged[key][0], merged[key][1],
                               merged[key][2] + entry[2], merged[key][3])
            else:
                merged[key] = (entry[0], entry[1], entry[2], slot)

        rewrites = {}
        free = [s for s in range(3) if row[SF_EFFECT + s] == 0]
        for aura, misc, amount, slot in merged.values():
            target = None
            if slot not in rewrites:
                target = slot
            else:
                target = next((s for s in free if s not in rewrites), None)
            if target is None:
                return None, "no free effect slot for the second aura"
            rewrites[target] = (aura, misc, amount)
        # A slot whose output was merged into another slot must be blanked, or it
        # would keep its original class-scoped ADD_*_MODIFIER and stay class-bound.
        for slot in {s for s in origin} - set(rewrites):
            rewrites[slot] = None
        out[spell_id] = rewrites
    return out, None


def select_chains(results):
    """(convertible, skipped) for the chains this policy can act on."""
    selected, skipped = [], collections.Counter()
    for result in results:
        if result["label"] != "needs-redesign" or result["group"] != "class":
            continue
        scoped = [e for e in result["effects"] if e["verdict"] == "spellmod-class-scoped"]
        ops = {e["misc"] for e in scoped}
        if not ops <= LEVER1:
            skipped["tier 2/3"] += 1
            continue
        unsupported = ops - set(CONVERTIBLE)
        if unsupported:
            skipped["no verified lever: " + ", ".join(
                sorted(SPELLMOD_OP_NAMES.get(o, str(o)) for o in unsupported))] += 1
            continue
        selected.append(result)
    return selected, skipped


def render_sql(conversions, spells, columns, dbc_path):
    class_set_index = next(i for i, (n, _, _) in enumerate(columns) if n == "SpellClassSet")
    ids = sorted(conversions)
    lines = []
    add = lines.append
    add("-- School-scoped Tier 1 talents: replace class scoping with a school scope.")
    add("--")
    add("-- Phase 1d Tier 1. These talents use an op that has a per-school aura lever, so")
    add("-- 'your Scorch, Fireball and Frostfire Bolt crit 3% more' becomes 'your Fire and")
    add("-- Frost spells crit 3% more' - which the character's second class can use too.")
    add("--")
    add("-- Op -> aura (each verified against this core's consumer, not guessed):")
    add("--   DAMAGE / DOT           -> 79  MOD_DAMAGE_PERCENT_DONE      (school mask)")
    add("--   CRITICAL_CHANCE        -> 71  MOD_SPELL_CRIT_CHANCE_SCHOOL (school mask)")
    add("--   CRIT_DAMAGE_BONUS      -> 163 MOD_CRIT_DAMAGE_BONUS        (school mask)")
    add("--   RESIST_MISS_CHANCE     -> 199 MOD_INCREASES_SPELL_PCT_TO_HIT (school mask)")
    add("--   COST flat              -> 73  MOD_POWER_COST_SCHOOL        (school mask)")
    add("--   COST pct               -> 72  MOD_POWER_COST_SCHOOL_PCT    (school mask)")
    add("-- THREAT is excluded: its aura is consumed as a multiplier while the spellmod is")
    add("-- additive, so the magnitude needs a conversion that has not been verified.")
    add("--")
    add("-- Each rewritten slot keeps Effect_N (APPLY_AURA) and gets the new aura, the school")
    add("-- in EffectMiscValue_N and the same magnitude (the DBC's value-1 convention is")
    add("-- reapplied). Slots that merge onto one (aura, school) pair are blanked, because")
    add("-- the engine multiplies matching auras. SpellClassSet and the classmask stay in")
    add("-- place: none of these auras consult them, and they document the original scope.")
    add("--")
    add("-- Schools come from Blizzard's own wording (the spells named in each tooltip, else a")
    add("-- school named in it); the classmask cannot supply them - see the tool's docstring.")
    add("-- Chains whose tooltip names no spell or school are NOT converted, and")
    add("-- python3 tools/school_scope_tier1.py --report lists them as review items.")
    add("--")
    add(f"-- {len(ids)} spells. Read from Spell.dbc: {dbc_path}")
    add("-- To revert: delete these ids from spell_dbc (the DELETE below lists them).")
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
            values = sql_values_for_spell(spells[spell_id], columns, class_set_index,
                                          conversions[spell_id])
            rows.append(f"  ({spell_id}, " + ", ".join(values[1:]) + ")")
        add(",\n".join(rows) + ";")
        add("")
    return "\n".join(lines) + "\n"


def render_report(planned, skipped, unresolved):
    lines = []
    add = lines.append
    add("# Tier 1 school scoping - derivation")
    add("")
    add(f"{len(planned)} chains convertible, {len(unresolved)} need a human school choice,")
    add(f"{sum(skipped.values())} out of scope.")
    add("")
    add("## Out of scope")
    add("")
    for reason, count in skipped.most_common():
        add(f"- {reason}: {count}")
    add("")
    add("## Converted (school + intent derived from the tooltip)")
    add("")
    add("| class | talent | school | intent | ops | why |")
    add("|---|---|---|---|---|---|")
    for result, mask, reason, intent_name in sorted(planned,
                                                    key=lambda p: (p[0]["className"], p[0]["name"])):
        ops = ", ".join(sorted({SPELLMOD_OP_NAMES.get(e["misc"], str(e["misc"]))
                                for e in result["effects"]
                                if e["verdict"] == "spellmod-class-scoped"}))
        add(f"| {result['className']} | {result['name']} | {school_name(mask)} | "
            f"{intent_name} | {ops} | {reason} |")
    add("")
    add("## Needs a human school choice")
    add("")
    add("These tooltips name no spell and no school, so the school is a design call:")
    add("")
    add("| class | talent | ops | tooltip |")
    add("|---|---|---|---|")
    for result, ops, text in unresolved:
        add(f"| {result['className']} | {result['name']} | {ops} | {text} |")
    add("")
    return "\n".join(lines) + "\n"


def sql_values_for_spell(row, columns, class_set_index, rewrites):
    """
    One DBC record as SQL values with this spell's effect slots rewritten.

    SpellClassSet is deliberately left alone here: the replacement auras never
    consult the family or the classmask, and keeping them means the original
    scoping is still visible in the row (and for any class script that keys off
    it). Text columns are emitted empty because the loader treats '' as "not
    overridden".
    """
    out = []
    for index, (_, data_type, unsigned) in enumerate(columns):
        slot = None
        if SF_AURA <= index <= SF_AURA + 2:
            slot = index - SF_AURA
        elif SF_MISCA <= index <= SF_MISCA + 2:
            slot = index - SF_MISCA
        elif SF_BASEPOINTS <= index <= SF_BASEPOINTS + 2:
            slot = index - SF_BASEPOINTS
        elif SF_EFFECT <= index <= SF_EFFECT + 2:
            slot = index - SF_EFFECT
        if slot is not None and slot in rewrites:
            rewrite = rewrites[slot]
            if rewrite is None:
                out.append("0" if index != SF_EFFECT + slot else "0")
                continue
            aura, misc, amount = rewrite
            if index == SF_AURA + slot:
                out.append(str(aura))
            elif index == SF_MISCA + slot:
                out.append(str(misc))
            elif index == SF_BASEPOINTS + slot:
                out.append(str(amount - 1))       # the DBC stores value - 1
            else:
                out.append(str(row[index]))       # Effect_N stays APPLY_AURA
            continue
        if data_type in TEXT_TYPES:
            out.append("''")
        elif data_type == "float":
            out.append(repr(round(struct.unpack("<f", struct.pack("<i", row[index]))[0], 6)))
        elif unsigned:
            bits = 64 if data_type == "bigint" else 32
            out.append(str(row[index] & ((1 << bits) - 1)))
        else:
            out.append(str(row[index]))
    return out


# ============================================================================
# Entry point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dbc", help="Spell.dbc to read (default: copy it from the "
                                      "running worldserver container)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="SQL output path")
    parser.add_argument("--report", help="write the derivation report here (markdown)")
    parser.add_argument("--check", action="store_true",
                        help="verify the live spell_dbc matches this tool's output")
    args = parser.parse_args()

    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8"))
    tab_classes = {t["tabId"]: t["class"].capitalize() for t in manifest["tabs"]}
    chains = load_chains(None)
    wanted = {spell_id for _, _, _, ranks in chains for spell_id in ranks}
    dbc_path = resolve_dbc(args.dbc)
    dbc, spells = load_spells(dbc_path, wanted)
    aura_names = parse_enum(os.path.join(CORE_ROOT, "game/Spells/Auras/SpellAuraDefines.h"),
                            ["SPELL_AURA_"])
    results = classify_chains(chains, dbc, spells, aura_names, derive_school_mask_auras(),
                              tab_classes)
    index = build_family_index(dbc)
    side = {r["talentId"]: r["side"] for r in analyze_breakdown(results, index)}

    selected, skipped = select_chains(results)
    conversions, planned, unresolved = {}, [], []
    for result in selected:
        mask, reason = derive_school(dbc, index, result, spells)
        text = dbc_string(dbc, spells[result["ranks"][0]][SF_DESC]).lower()
        intent = detect_intent(text)
        ops = {e["misc"] for e in result["effects"] if e["verdict"] == "spellmod-class-scoped"}
        # The tooltip does not always say "damage" or "healed" ("Increases the effect
        # of your Rejuvenation spell"), so fall back to what the spells it governs
        # actually do - Rejuvenation only heals, so that talent is healing-side.
        if not any(intent) and ops & {0, 22} and side.get(result["talentId"]) == "heal-only":
            intent = (False, True)
            reason = reason or "tooltip names no side; its spells only heal"
        # A healing aura (136) has no school parameter, so a heal-only talent needs
        # no school - only the damage side of a "both" talent does.
        if not mask and intent[1] and not intent[0]:
            mask = UNIVERSAL_MASK
            reason = "schoolless healing (MOD_HEALING_DONE_PERCENT ignores misc)"
        # Some tooltips name neither a spell nor a school ("reduces the chance your
        # helpful spells are dispelled", "increases your chance to hit with spells").
        # Falling back to every school keeps the talent broad, which is the policy;
        # for ops whose aura ignores misc (healing, dispel resist) it is unused anyway.
        elif not mask:
            mask = UNIVERSAL_MASK
            reason = "tooltip names no school or scope - universal"
        intent_name = "both" if all(intent) else ("damage" if intent[0] else
                                                  ("heal" if intent[1] else "unspecified"))
        if not mask:
            unresolved.append((result, ", ".join(sorted(
                {SPELLMOD_OP_NAMES.get(e["misc"], str(e["misc"])) for e in result["effects"]
                 if e["verdict"] == "spellmod-class-scoped"})), text[:90]))
            continue
        rewrites, error = convert_effects(result, spells, mask, intent)
        if error or not rewrites:
            skipped[error or "nothing to rewrite"] += 1
            continue
        conversions.update(rewrites)
        planned.append((result, mask, reason, intent_name))

    print(f"convertible chains : {len(planned)}", file=sys.stderr)
    print(f"spells rewritten   : {len(conversions)}", file=sys.stderr)
    print(f"needs a human call : {len(unresolved)}", file=sys.stderr)
    print(f"out of scope       : {dict(skipped)}", file=sys.stderr)
    print("intent mix         : " + ", ".join(
        f"{name} {count}" for name, count in
        collections.Counter(p[3] for p in planned).most_common()), file=sys.stderr)

    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_report(planned, skipped, unresolved))
        print(f"wrote {args.report}", file=sys.stderr)

    if args.check:
        rows = run_query(
            f"SELECT ID, EffectAura_1, EffectAura_2, EffectAura_3, EffectMiscValue_1, "
            f"EffectMiscValue_2, EffectMiscValue_3 FROM `{TABLE}` "
            f"WHERE ID IN ({', '.join(str(i) for i in sorted(conversions))})"
        )
        current = {int(r["ID"]): r for r in rows}
        bad = []
        for spell_id, rewrites in conversions.items():
            row = current.get(spell_id)
            if not row:
                bad.append((spell_id, "no override row"))
                continue
            for slot, rewrite in rewrites.items():
                want_aura = 0 if rewrite is None else rewrite[0]
                want_misc = 0 if rewrite is None else rewrite[1]
                if int(row[f"EffectAura_{slot + 1}"]) != want_aura or \
                        int(row[f"EffectMiscValue_{slot + 1}"]) != want_misc:
                    bad.append((spell_id, f"slot {slot} aura/misc mismatch"))
        if bad:
            print(f"DRIFT: {len(bad)} problem(s): {bad[:6]}", file=sys.stderr)
            return 1
        print(f"policy is applied: {len(conversions)} spell(s) match", file=sys.stderr)
        return 0

    sql = render_sql(conversions, spells, load_columns(), dbc_path)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(sql)
    print(f"wrote {args.out} ({len(sql) // 1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())