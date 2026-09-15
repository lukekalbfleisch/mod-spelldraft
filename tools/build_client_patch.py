#!/usr/bin/env python3
"""Build the SpellDraft client patch (patch-P.mpq) + matching server SQL.

Custom glyphs need three client-side DBC additions (icons, socket gating, panel
tooltips): Item.dbc, Spell.dbc and GlyphProperties.dbc. The client replaces
whole files from patch archives, so this tool appends our rows to the NATIVE
files and packs the results into a fresh MPQ (v1, plain uncompressed storage —
readable by the stock 3.3.5 client and by mpyq for verification).

New records are cloned from native template records (no field-layout
archaeology): apply spells clone 54854 (a native glyph apply), marker auras
clone 54292 (the beta White Bear dummy aura), items clone the Item.dbc row of
native glyph item 43336.

Inputs:
    tools/client_patch_manifest.json   glyph definitions (single source of truth)
    --dbc-src DIR                      native Item.dbc / Spell.dbc / GlyphProperties.dbc
                                       (docker cp them from ac-worldserver:/azerothcore/env/dist/data/dbc)
Outputs:
    wow-client/Data/patch-P.mpq
    data/sql/db-world/25_custom_glyphs_client.sql
"""

import argparse
import json
import struct
from pathlib import Path

MODULE = Path(__file__).resolve().parent.parent

APPLY_TEMPLATE_SPELL = 54854   # native "Glyph of Frenzied Regeneration" apply spell
MARKER_TEMPLATE_SPELL = 54292  # native beta "Glyph of the White Bear" dummy aura
ITEM_TEMPLATE_ENTRY = 43336    # native beta glyph item (class 16)

SPELL_ID_FIELD = 0
SPELL_MISCVALUE1_FIELD = 110
SPELL_ICON_FIELD = 133
SPELL_NAME_FIELD = 136
SPELL_DESC_FIELD = 170

# --- generic custom active spells (tools/eq_spell_pack.json) -----------------
# Neutral base row: native Crippling Poison. Chosen because every field that
# would otherwise leak into a clone is already inert on it - no Attributes, no
# Stances, SpellFamilyName 0, no cooldown/mana, EquippedItemClass -1. Every
# field that matters is then set explicitly below, so nothing is inherited by
# accident. Field indices are from SpellEntry in
# src/server/shared/DataStores/DBCStructure.h.
EQ_BASE_TEMPLATE = 25809
EQ_CUSTOM_FAMILY = 220


def bitmask32(bit):
    """1 << bit as a two's-complement signed int32 (DBC fields pack as 'i',
    but classmask/flag words are really raw uint32 bit patterns - bit 31
    overflows signed range without this)."""
    v = 1 << bit
    return v - 0x100000000 if v >= 0x80000000 else v

SF_CATEGORY, SF_DISPEL, SF_MECHANIC = 1, 2, 3
SF_ATTR0, SF_STANCES, SF_TARGETS = 4, 12, 16
SF_CASTTIME, SF_RECOVERY, SF_CATRECOVERY = 28, 29, 30
SF_PROCFLAGS, SF_PROCCHANCE, SF_PROCCHARGES = 34, 35, 36
SF_MAXLEVEL, SF_BASELEVEL, SF_SPELLLEVEL = 37, 38, 39
SF_DURATION, SF_POWERTYPE, SF_MANACOST = 40, 41, 42
SF_RANGE, SF_STACK, SF_EQUIPCLASS = 46, 49, 68
SF_EFFECT, SF_DIESIDES, SF_REALPPL, SF_BASEPOINTS = 71, 74, 77, 80
SF_EFFMECHANIC, SF_TARGETA, SF_TARGETB, SF_RADIUS = 83, 86, 89, 92
SF_AURA, SF_AMPLITUDE, SF_VALUEMULT, SF_CHAINTARGET = 95, 98, 101, 104
SF_ITEMTYPE, SF_MISCA, SF_MISCB, SF_TRIGGER, SF_COMBOPTS = 107, 110, 113, 116, 119
SF_CLASSMASK = 122
SF_VISUAL, SF_ICON = 131, 133
SF_NAME, SF_RANK, SF_DESC, SF_TOOLTIP = 136, 153, 170, 187
SF_MANAPCT, SF_FAMILY, SF_FAMILYFLAGS = 204, 208, 209
SF_MAXTARGETS, SF_DMGCLASS, SF_PREVENTION, SF_SCHOOL = 212, 213, 214, 225


def build_eq_spell_row(spells, base, spec):
    """Clone the neutral base row and apply this spell's explicit overrides."""
    row = list(base)
    row[SPELL_ID_FIELD] = spec['id']
    row[SF_CATEGORY] = row[SF_DISPEL] = 0
    row[SF_MECHANIC] = spec.get('mechanic', 0)
    for i in range(SF_ATTR0, SF_ATTR0 + 8):
        row[i] = 0
    for i in range(SF_STANCES, SF_STANCES + 4):
        row[i] = 0
    row[SF_TARGETS] = 0
    row[SF_CASTTIME] = spec.get('cast_idx', 1)
    row[SF_RECOVERY] = spec.get('cooldown', 0)
    row[SF_CATRECOVERY] = 0
    row[SF_PROCFLAGS] = spec.get('proc_flags', 0)
    row[SF_PROCCHANCE] = spec.get('proc_chance', 101)
    row[SF_PROCCHARGES] = 0
    row[SF_MAXLEVEL] = 0
    row[SF_BASELEVEL] = row[SF_SPELLLEVEL] = spec.get('level', 1)
    row[SF_DURATION] = spec.get('duration_idx', 0)
    row[SF_POWERTYPE] = 0
    row[SF_MANACOST] = 0          # free by design; this pack is deliberately overtuned
    row[SF_RANGE] = spec.get('range_idx', 4)
    row[SF_STACK] = 0
    row[SF_EQUIPCLASS] = -1

    for e in range(3):
        for field in (SF_EFFECT, SF_DIESIDES, SF_REALPPL, SF_BASEPOINTS, SF_EFFMECHANIC,
                      SF_TARGETA, SF_TARGETB, SF_RADIUS, SF_AURA, SF_AMPLITUDE,
                      SF_VALUEMULT, SF_CHAINTARGET, SF_ITEMTYPE, SF_MISCA, SF_MISCB,
                      SF_TRIGGER, SF_COMBOPTS):
            row[field + e] = 0
    for i in range(SF_CLASSMASK, SF_CLASSMASK + 9):
        row[i] = 0

    for i, ef in enumerate(spec['effects'][:3]):
        row[SF_EFFECT + i] = ef['type']
        row[SF_DIESIDES + i] = ef.get('die_sides', 1)
        # DBC stores basepoints as (value - 1); the engine adds 1 + die roll.
        row[SF_BASEPOINTS + i] = ef.get('value', 0) - 1
        row[SF_EFFMECHANIC + i] = ef.get('mechanic', 0)
        row[SF_TARGETA + i] = ef.get('target_a', 0)
        row[SF_TARGETB + i] = ef.get('target_b', 0)
        row[SF_RADIUS + i] = ef.get('radius_idx', 0)
        row[SF_AURA + i] = ef.get('aura', 0)
        row[SF_AMPLITUDE + i] = ef.get('amplitude', 0)
        row[SF_MISCA + i] = ef.get('misc_a', 0)
        row[SF_MISCB + i] = ef.get('misc_b', 0)
        row[SF_TRIGGER + i] = ef.get('trigger', 0)

    row[SF_VISUAL] = spec.get('visual', 0)
    row[SF_VISUAL + 1] = 0
    row[SF_ICON] = spec['icon']
    row[SF_NAME] = spells.add_string(spec['name'])
    row[SF_RANK] = spells.add_string(spec['rank_text']) if spec.get('rank_text') else 0
    row[SF_DESC] = spells.add_string(spec['tooltip'])
    row[SF_TOOLTIP] = spells.add_string(spec['tooltip'])
    row[SF_MANAPCT] = 0
    # Shared custom family (never collides with a real WotLK SPELLFAMILY_*),
    # one classmask bit per distinct spell (spells sharing a `name`, e.g. a
    # rank chain, share a bit) so a talent's native SpellMod aura can target
    # exactly one of our spells via EffectSpellClassMask, the same mechanism
    # real "Improved <Spell>" talents use. See tools/eq_talent_pack.json.
    if 'family_bit' in spec:
        row[SF_FAMILY] = EQ_CUSTOM_FAMILY
        row[SF_FAMILYFLAGS] = bitmask32(spec['family_bit'])
        row[SF_FAMILYFLAGS + 1] = 0
        row[SF_FAMILYFLAGS + 2] = 0
    else:
        row[SF_FAMILY] = 0
        for i in range(SF_FAMILYFLAGS, SF_FAMILYFLAGS + 3):
            row[i] = 0
    row[SF_MAXTARGETS] = spec.get('max_targets', 0)
    row[SF_DMGCLASS] = 1
    row[SF_PREVENTION] = 0
    row[SF_SCHOOL] = spec.get('school', 1)
    return row


# ============================================================================
# EQ talent pack: passive SpellMod talents that modify EQ pack spells
# ============================================================================

def build_eq_talent_row(spells, base, spec):
    """A passive, self-targeted talent spell carrying up to 3 native SpellMod
    aura effects (flat or pct), each aimed at one EQ spell via the shared
    custom family + a single classmask bit. See tools/eq_talent_pack.json for
    the verified mechanism this relies on."""
    row = list(base)
    row[SPELL_ID_FIELD] = spec['id']
    row[SF_CATEGORY] = row[SF_DISPEL] = row[SF_MECHANIC] = 0
    for i in range(SF_ATTR0, SF_ATTR0 + 8):
        row[i] = 0
    for i in range(SF_STANCES, SF_STANCES + 4):
        row[i] = 0
    row[SF_TARGETS] = 0
    row[SF_CASTTIME] = 1          # instant (talents are passive, never cast directly)
    row[SF_RECOVERY] = row[SF_CATRECOVERY] = 0
    row[SF_PROCFLAGS] = row[SF_PROCCHARGES] = 0
    row[SF_PROCCHANCE] = 101
    row[SF_MAXLEVEL] = 0
    row[SF_BASELEVEL] = row[SF_SPELLLEVEL] = 0
    row[SF_DURATION] = 0          # permanent while known (learned passive, not a timed buff)
    row[SF_POWERTYPE] = 0
    row[SF_MANACOST] = 0
    row[SF_RANGE] = 1
    row[SF_STACK] = 0
    row[SF_EQUIPCLASS] = -1

    target_mask = bitmask32(spec['target_bit'])
    for e in range(3):
        for field in (SF_EFFECT, SF_DIESIDES, SF_REALPPL, SF_BASEPOINTS, SF_EFFMECHANIC,
                      SF_TARGETA, SF_TARGETB, SF_RADIUS, SF_AURA, SF_AMPLITUDE,
                      SF_VALUEMULT, SF_CHAINTARGET, SF_ITEMTYPE, SF_MISCA, SF_MISCB,
                      SF_TRIGGER, SF_COMBOPTS):
            row[field + e] = 0
        for j in range(3):
            row[SF_CLASSMASK + e * 3 + j] = 0

    for i, mod in enumerate(spec['mods'][:3]):
        row[SF_EFFECT + i] = 6  # SPELL_EFFECT_APPLY_AURA
        row[SF_DIESIDES + i] = 1
        row[SF_AURA + i] = 108 if mod['kind'] == 'pct' else 107  # ADD_PCT/FLAT_MODIFIER
        row[SF_BASEPOINTS + i] = mod['value'] - 1
        row[SF_TARGETA + i] = 1   # TARGET_UNIT_CASTER
        row[SF_MISCA + i] = mod['op']  # SpellModOp
        row[SF_CLASSMASK + i * 3] = target_mask  # which EQ spell this effect affects

    row[SF_VISUAL] = 0
    row[SF_VISUAL + 1] = 0
    row[SF_ICON] = spec['icon']
    row[SF_NAME] = spells.add_string(spec['name'])
    row[SF_RANK] = 0
    row[SF_DESC] = spells.add_string(spec['tooltip'])
    row[SF_TOOLTIP] = spells.add_string(spec['tooltip'])
    row[SF_MANAPCT] = 0
    row[SF_FAMILY] = 0
    for i in range(SF_FAMILYFLAGS, SF_FAMILYFLAGS + 3):
        row[i] = 0
    row[SF_MAXTARGETS] = 0
    row[SF_DMGCLASS] = 0
    row[SF_PREVENTION] = 0
    row[SF_SCHOOL] = 1
    return row


def build_marker_row(spells, base, spell_id, name, tooltip, icon):
    """A minimal passive spell whose only effect is SPELL_AURA_DUMMY (4) - the
    exact shape spell_pet_auras requires of its trigger spell (SpellMgr.cpp's
    loader rejects anything else: "does not have dummy aura or dummy effect").
    Used as the learned talent passive for every pet-buff talent; the actual
    buff lives in a separate spell applied to the pet (see build_pet_buff_row
    and emit_pet_auras_sql)."""
    row = list(base)
    row[SPELL_ID_FIELD] = spell_id
    row[SF_CATEGORY] = row[SF_DISPEL] = row[SF_MECHANIC] = 0
    for i in range(SF_ATTR0, SF_ATTR0 + 8):
        row[i] = 0
    for i in range(SF_STANCES, SF_STANCES + 4):
        row[i] = 0
    row[SF_TARGETS] = 0
    row[SF_CASTTIME] = 1
    row[SF_RECOVERY] = row[SF_CATRECOVERY] = 0
    row[SF_PROCFLAGS] = row[SF_PROCCHARGES] = 0
    row[SF_PROCCHANCE] = 101
    row[SF_MAXLEVEL] = row[SF_BASELEVEL] = row[SF_SPELLLEVEL] = 0
    row[SF_DURATION] = 0
    row[SF_POWERTYPE] = row[SF_MANACOST] = 0
    row[SF_RANGE] = 1
    row[SF_STACK] = 0
    row[SF_EQUIPCLASS] = -1
    for e in range(3):
        for field in (SF_EFFECT, SF_DIESIDES, SF_REALPPL, SF_BASEPOINTS, SF_EFFMECHANIC,
                      SF_TARGETA, SF_TARGETB, SF_RADIUS, SF_AURA, SF_AMPLITUDE,
                      SF_VALUEMULT, SF_CHAINTARGET, SF_ITEMTYPE, SF_MISCA, SF_MISCB,
                      SF_TRIGGER, SF_COMBOPTS):
            row[field + e] = 0
        for j in range(3):
            row[SF_CLASSMASK + e * 3 + j] = 0
    # Effect1: SPELL_AURA_DUMMY (4) - required shape for spell_pet_auras.
    row[SF_EFFECT] = 6
    row[SF_DIESIDES] = 1
    row[SF_AURA] = 4
    row[SF_BASEPOINTS] = -1
    row[SF_TARGETA] = 1
    row[SF_VISUAL] = row[SF_VISUAL + 1] = 0
    row[SF_ICON] = icon
    row[SF_NAME] = spells.add_string(name)
    row[SF_RANK] = 0
    row[SF_DESC] = spells.add_string(tooltip)
    row[SF_TOOLTIP] = spells.add_string(tooltip)
    row[SF_MANAPCT] = 0
    row[SF_FAMILY] = 0
    for i in range(SF_FAMILYFLAGS, SF_FAMILYFLAGS + 3):
        row[i] = 0
    row[SF_MAXTARGETS] = 0
    row[SF_DMGCLASS] = 0
    row[SF_PREVENTION] = 0
    row[SF_SCHOOL] = 1
    return row


def build_pet_buff_row(spells, base, spec):
    """A real aura spell, self-targeted (TargetA=1), cast directly onto a pet
    Unit by the engine's native spell_pet_auras pipeline (Unit::CastPetAura ->
    CastSpell(this, auraId, true) - "this" is the pet, so effect target 1
    resolves to the pet itself). This is NOT a SpellMod: SpellModifier
    registration requires target->IsPlayer() (AuraEffect::ApplySpellMod,
    SpellAuraEffects.cpp:813), which a Pet never is - so these must be plain
    stat/damage auras, generically applicable to any Unit."""
    row = list(base)
    row[SPELL_ID_FIELD] = spec['spell_id']
    row[SF_CATEGORY] = row[SF_DISPEL] = row[SF_MECHANIC] = 0
    for i in range(SF_ATTR0, SF_ATTR0 + 8):
        row[i] = 0
    for i in range(SF_STANCES, SF_STANCES + 4):
        row[i] = 0
    row[SF_TARGETS] = 0
    row[SF_CASTTIME] = 1
    row[SF_RECOVERY] = row[SF_CATRECOVERY] = 0
    row[SF_PROCFLAGS] = row[SF_PROCCHARGES] = 0
    row[SF_PROCCHANCE] = 101
    row[SF_MAXLEVEL] = row[SF_BASELEVEL] = row[SF_SPELLLEVEL] = 0
    row[SF_DURATION] = 0
    row[SF_POWERTYPE] = row[SF_MANACOST] = 0
    row[SF_RANGE] = 1
    row[SF_STACK] = 0
    row[SF_EQUIPCLASS] = -1
    for e in range(3):
        for field in (SF_EFFECT, SF_DIESIDES, SF_REALPPL, SF_BASEPOINTS, SF_EFFMECHANIC,
                      SF_TARGETA, SF_TARGETB, SF_RADIUS, SF_AURA, SF_AMPLITUDE,
                      SF_VALUEMULT, SF_CHAINTARGET, SF_ITEMTYPE, SF_MISCA, SF_MISCB,
                      SF_TRIGGER, SF_COMBOPTS):
            row[field + e] = 0
        for j in range(3):
            row[SF_CLASSMASK + e * 3 + j] = 0
    for i, ef in enumerate(spec['effects'][:3]):
        row[SF_EFFECT + i] = 6
        row[SF_DIESIDES + i] = 1
        row[SF_AURA + i] = ef['aura']
        row[SF_BASEPOINTS + i] = ef['value'] - 1
        row[SF_TARGETA + i] = ef.get('target_a', 1)
        row[SF_MISCA + i] = ef.get('misc_a', 0)
    row[SF_VISUAL] = row[SF_VISUAL + 1] = 0
    row[SF_ICON] = spec['icon']
    row[SF_NAME] = spells.add_string(spec['name'])
    row[SF_RANK] = 0
    row[SF_DESC] = spells.add_string(spec['tooltip'])
    row[SF_TOOLTIP] = spells.add_string(spec['tooltip'])
    row[SF_MANAPCT] = 0
    row[SF_FAMILY] = 0
    for i in range(SF_FAMILYFLAGS, SF_FAMILYFLAGS + 3):
        row[i] = 0
    row[SF_MAXTARGETS] = 0
    row[SF_DMGCLASS] = 0
    row[SF_PREVENTION] = 0
    row[SF_SCHOOL] = 1
    return row


def emit_eq_talent_sql(talent_pack, dest):
    lines = [
        '-- Passive talents modifying the EQ spell pack (28_eq_spell_pack.sql).',
        '-- GENERATED by tools/build_client_patch.py from tools/eq_talent_pack.json.',
        '-- Do not edit by hand.',
        '--',
        '-- Each talent is a single-rank talent_dbc chain whose rank spell lives in',
        '-- the patched Spell.dbc (client patch-P.mpq / server dbc/Spell.dbc). None',
        '-- of these are in LOCKED_TALENTS, so they are purchasable with ordinary',
        '-- Talent Points rather than Tome-of-Talents-only.',
        '',
    ]
    talents = talent_pack['talents']
    # Deletes the WHOLE reserved block (90001-90999), not just currently-defined
    # IDs, so removing/renumbering a talent between regenerations can't leave an
    # orphaned row pointing at a spell ID no longer in Spell.dbc.
    lines.append('DELETE FROM `talent_dbc` WHERE `ID` BETWEEN 90001 AND 90999;')
    lines.append('INSERT INTO `talent_dbc` (`ID`, `TabID`, `TierID`, `ColumnIndex`, `SpellRank_1`) VALUES')
    rows = [f"    ({t['talent_id']}, 0, {t['tier']}, 0, {t['id']})" for t in talents]
    lines.append(',\n'.join(rows) + ';')

    pet_talents = [t for t in talents if 'pet_buff' in t]
    if pet_talents:
        lines += [
            '',
            '-- Native pet-buff pipeline (Unit::AddPetAura / CastPetAura): when the',
            '-- owner has the dummy-aura talent passive, `aura` is cast directly on',
            '-- their pet (filtered to `pet` creature entry, 0 = any), reactively -',
            '-- applies immediately even if the pet is already summoned, and removed',
            '-- again if the talent is respecced away.',
            f"DELETE FROM `spell_pet_auras` WHERE `spell` IN ({', '.join(str(t['id']) for t in pet_talents)});",
            'INSERT INTO `spell_pet_auras` (`spell`, `effectId`, `pet`, `aura`) VALUES',
        ]
        rows = [f"    ({t['id']}, 0, {t['pet_buff']['creature_entry']}, {t['pet_buff']['buff_spell_id']})"
                for t in pet_talents]
        lines.append(',\n'.join(rows) + ';')

    lines.append('')
    Path(dest).write_text('\n'.join(lines))


def build_eq_talents(spells, eq_base, talent_pack):
    """Returns the list of newly-built Spell.dbc rows for the talent pack."""
    new_rows = []
    for t in talent_pack['talents']:
        if 'pet_buff' in t:
            new_rows.append(build_marker_row(spells, eq_base, t['id'], t['name'], t['tooltip'], t['icon']))
            pb = t['pet_buff']
            new_rows.append(build_pet_buff_row(spells, eq_base, {
                'spell_id': pb['buff_spell_id'], 'name': pb.get('buff_name', t['name']),
                'tooltip': pb.get('buff_tooltip', t['tooltip']), 'icon': pb.get('buff_icon', t['icon']),
                'effects': pb['effects'],
            }))
        else:
            new_rows.append(build_eq_talent_row(spells, eq_base, t))
    return new_rows


def emit_eq_spell_sql(pack, dest):
    """Draft-pool rows. The engine itself reads the patched Spell.dbc (deployed
    by install.sh), so NO spell_dbc rows are written here on purpose: DBCStore
    SetEntry() replaces a whole record, so a partial spell_dbc row would clobber
    the complete DBC one. These tables are the module's Lua-only mirror, queried
    by LoadValidSpellChoices() in lua/SpellDraft/spell_choice.lua."""
    sl = pack['skill_line']
    draftable = [s for s in pack['spells'] if s.get('draftable', True)]
    all_ids = [s['id'] for s in pack['spells']]

    lines = [
        '-- EverQuest-inspired custom spell pack (draft-pool registration).',
        '-- GENERATED by tools/build_client_patch.py from tools/eq_spell_pack.json.',
        '-- Do not edit by hand.',
        '--',
        '-- The spells themselves live in the patched Spell.dbc shipped by',
        '-- wow-client/Data/patch-P.mpq (client) and dbc/Spell.dbc (server, deployed',
        '-- by install.sh). These tables only make them visible to the draft picker.',
        '',
        f'DELETE FROM `dbc_skillline` WHERE `ID` = {sl["id"]};',
        'INSERT INTO `dbc_skillline` (`ID`, `CategoryID`, `DisplayName_Lang_enUS`) VALUES',
        f"    ({sl['id']}, {sl['category']}, '{sql_escape(sl['name'])}');",
        '',
        f"DELETE FROM `dbc_skilllineability` WHERE `Spell` IN ({', '.join(str(i) for i in all_ids)});",
        'INSERT INTO `dbc_skilllineability` (`ID`, `SkillLine`, `Spell`, `RaceMask`, `ClassMask`) VALUES',
    ]
    rows = [f"    ({1100000 + i}, {sl['id']}, {s['id']}, 0, 0)" for i, s in enumerate(draftable)]
    lines.append(',\n'.join(rows) + ';')

    lines += [
        '',
        f"DELETE FROM `dbc_spells` WHERE `ID` IN ({', '.join(str(i) for i in all_ids)});",
        'INSERT INTO `dbc_spells`',
        '    (`ID`, `Category`, `Attributes`, `MaxLevel`, `SpellLevel`, `DurationIndex`,',
        '     `Effect_1`, `Effect_2`, `Effect_3`, `SpellIconID`, `Rarity`,',
        '     `Name_Lang_enUS`, `Description_Lang_enUS`) VALUES',
    ]
    rows = []
    for s in draftable:
        eff = [0, 0, 0]
        for i, e in enumerate(s['effects'][:3]):
            eff[i] = e['type']
        rows.append(f"    ({s['id']}, 0, 0, 0, {s.get('level', 1)}, {s.get('duration_idx', 0)},"
                    f" {eff[0]}, {eff[1]}, {eff[2]}, {s['icon']}, {s['rarity']},"
                    f" '{sql_escape(s['name'])}', '{sql_escape(s['tooltip'])}')")
    lines.append(',\n'.join(rows) + ';')
    lines.append('')

    Path(dest).write_text('\n'.join(lines))

# ============================================================================
# MPQ v1 writer (plain multi-sector, uncompressed)
# ============================================================================

def _build_crypt_table():
    table = [0] * 0x500
    seed = 0x00100001
    for index1 in range(0x100):
        index2 = index1
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp1 = (seed & 0xFFFF) << 0x10
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp2 = seed & 0xFFFF
            table[index2] = temp1 | temp2
            index2 += 0x100
    return table

_CRYPT = _build_crypt_table()


def _hash_string(s, hash_type):
    seed1, seed2 = 0x7FED7FED, 0xEEEEEEEE
    for ch in s.upper():
        value = _CRYPT[(hash_type << 8) + ord(ch)]
        seed1 = (value ^ ((seed1 + seed2) & 0xFFFFFFFF)) & 0xFFFFFFFF
        seed2 = (ord(ch) + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1


def _encrypt(words, key):
    seed = 0xEEEEEEEE
    out = []
    for word in words:
        seed = (seed + _CRYPT[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        out.append(word ^ ((key + seed) & 0xFFFFFFFF))
        key = (((~key << 0x15) + 0x11111111) | (key >> 0x0B)) & 0xFFFFFFFF
        seed = (word + seed + (seed << 5) + 3) & 0xFFFFFFFF
    return out


def write_mpq(dest, files):
    """files: dict of archive path (backslashes) -> bytes."""
    files = dict(files)
    files['(listfile)'] = ('\r\n'.join(files) + '\r\n').encode()

    hash_size = 1
    while hash_size < len(files) * 2:
        hash_size *= 2

    header_size = 32
    blobs, block_entries = [], []
    offset = header_size
    hash_entries = [[0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF]] * hash_size
    hash_entries = [list(e) for e in hash_entries]

    for block_index, (name, data) in enumerate(files.items()):
        blobs.append(data)
        # 0x80000000 EXISTS, stored raw as plain multi-sector (uncompressed
        # files carry no sector-offset table, so the payload is byte-identical).
        # Do NOT add 0x01000000 SINGLE_UNIT: the 3.3.5 client's async streaming
        # reader (used for .m2/.anim/.blp loaded during play) mishandles
        # single-unit files and corrupts the heap -> ERROR #132 on exit.
        block_entries.append((offset, len(data), len(data), 0x80000000))
        idx = _hash_string(name, 0) & (hash_size - 1)
        while hash_entries[idx][3] != 0xFFFFFFFF:
            idx = (idx + 1) & (hash_size - 1)
        hash_entries[idx] = [_hash_string(name, 1), _hash_string(name, 2), 0, block_index]
        offset += len(data)

    hash_words = []
    for e in hash_entries:
        hash_words += e
    block_words = []
    for e in block_entries:
        block_words += list(e)

    hash_data = struct.pack(f'<{len(hash_words)}I',
                            *_encrypt(hash_words, _hash_string('(hash table)', 3)))
    block_data = struct.pack(f'<{len(block_words)}I',
                             *_encrypt(block_words, _hash_string('(block table)', 3)))

    hash_pos = offset
    block_pos = hash_pos + len(hash_data)
    archive_size = block_pos + len(block_data)

    header = struct.pack('<4sIIHHIIII', b'MPQ\x1a', header_size, archive_size,
                         0, 3, hash_pos, block_pos, hash_size, len(block_entries))

    with open(dest, 'wb') as fh:
        fh.write(header)
        for blob in blobs:
            fh.write(blob)
        fh.write(hash_data)
        fh.write(block_data)


# ============================================================================
# DBC helpers
# ============================================================================

class Dbc:
    def __init__(self, path):
        data = open(path, 'rb').read()
        magic, self.recs, self.fields, self.recsize, self.strsize = \
            struct.unpack_from('<4sIIII', data, 0)
        assert magic == b'WDBC', path
        self.records = bytearray(data[20:20 + self.recs * self.recsize])
        self.strings = bytearray(data[20 + self.recs * self.recsize:])

    def get_record(self, rec_id):
        for i in range(self.recs):
            if struct.unpack_from('<I', self.records, i * self.recsize)[0] == rec_id:
                return list(struct.unpack_from(f'<{self.fields}i', self.records, i * self.recsize))
        raise KeyError(rec_id)

    def add_string(self, text):
        offset = len(self.strings)
        self.strings += text.encode('utf-8') + b'\x00'
        return offset

    def add_record(self, values):
        assert len(values) == self.fields
        self.records += struct.pack(f'<{self.fields}i', *values)
        self.recs += 1

    def dumps(self):
        return (struct.pack('<4sIIII', b'WDBC', self.recs, self.fields,
                            self.recsize, len(self.strings))
                + bytes(self.records) + bytes(self.strings))


# ============================================================================
# SQL emission (mirrors the client rows server-side)
# ============================================================================

def sql_escape(s):
    return s.replace('\\', '\\\\').replace("'", "\\'")


CMD_COLUMNS = ('ID', 'Flags', 'ModelName', 'SizeClass', 'ModelScale', 'BloodID',
               'FootprintTextureID', 'FootprintTextureLength', 'FootprintTextureWidth',
               'FootprintParticleScale', 'FoleyMaterialID', 'FootstepShakeSize',
               'DeathThudShakeSize', 'SoundID', 'CollisionWidth', 'CollisionHeight',
               'MountHeight', 'GeoBoxMinX', 'GeoBoxMinY', 'GeoBoxMinZ', 'GeoBoxMaxX',
               'GeoBoxMaxY', 'GeoBoxMaxZ', 'WorldEffectScale', 'AttachedEffectScale',
               'MissileCollisionRadius', 'MissileCollisionPush', 'MissileCollisionRaise')
CMD_FLOATS = {4, 7, 8, 9, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27}
CDI_COLUMNS = ('ID', 'ModelID', 'SoundID', 'ExtendedDisplayInfoID', 'CreatureModelScale',
               'CreatureModelAlpha', 'TextureVariation_1', 'TextureVariation_2',
               'TextureVariation_3', 'PortraitTextureName', 'BloodLevel', 'BloodID',
               'NPCSoundID', 'ParticleColorID', 'CreatureGeosetData', 'ObjectEffectPackageID')
CDI_FLOATS = {4}


def _sql_value(value, is_float):
    if isinstance(value, str):
        return "'" + sql_escape(value) + "'"
    if is_float:
        return repr(round(struct.unpack('<f', struct.pack('<i', value))[0], 6))
    return str(value)


def emit_creature_sql(lines, table, columns, floats, entries):
    if not entries:
        return
    ids = ', '.join(str(e['row'][0]) for e in entries)
    lines.append('')
    lines.append(f'DELETE FROM `{table}` WHERE `ID` IN ({ids});')
    lines.append(f"INSERT INTO `{table}` ({', '.join('`' + c + '`' for c in columns)}) VALUES")
    rows = []
    for e in entries:
        vals = [_sql_value(v, j in floats) for j, v in enumerate(e['row'])]
        rows.append('    (' + ', '.join(vals) + ')')
    lines.append(',\n'.join(rows) + ';')


def emit_sql(glyphs, manifest, dest):
    lines = [
        '-- Custom glyphs defined via the client patch pipeline.',
        '-- GENERATED by tools/build_client_patch.py from tools/client_patch_manifest.json',
        '-- (client side: wow-client/Data/patch-P.mpq). Do not edit by hand.',
        '',
        f"DELETE FROM `glyphproperties_dbc` WHERE `ID` IN ({', '.join(str(g['glyph_id']) for g in glyphs)});",
        'INSERT INTO `glyphproperties_dbc` (`ID`, `SpellID`, `GlyphSlotFlags`, `SpellIconID`) VALUES',
    ]
    rows = []
    for g in glyphs:
        flags = 1 if g['type'] == 'minor' else 0
        rows.append(f"    ({g['glyph_id']}, {g['effect_spell'] or g['marker_spell']}, {flags}, {g['socket_icon']})")
    lines.append(',\n'.join(rows) + ';')

    lines += [
        '',
        f"DELETE FROM `spell_dbc` WHERE `ID` IN ({', '.join(str(i) for g in glyphs for i in (g['apply_spell'], g['marker_spell']) if i)});",
        'INSERT INTO `spell_dbc`',
        '    (`ID`, `Attributes`, `AttributesEx`, `Targets`, `InterruptFlags`, `ProcChance`,',
        '     `CastingTimeIndex`, `DurationIndex`, `RangeIndex`, `EquippedItemClass`,',
        '     `Effect_1`, `ImplicitTargetA_1`, `EffectAura_1`, `EffectMiscValue_1`,',
        '     `SpellVisualID_1`, `SpellIconID`, `SchoolMask`, `Name_Lang_enUS`) VALUES',
    ]
    rows = []
    for g in glyphs:
        rows.append(f"    ({g['apply_spell']}, 268435456, 2048, 131072, 63, 101, 1, 0, 1, -1,"
                    f" 74, 0, 0, {g['glyph_id']}, 12369, {g['spell_icon']}, 1, '{sql_escape(g['name'])}')")
        if not g['effect_spell']:
            # Hidden passive dummy aura (Attributes 0xC0), self-target, infinite
            # duration (DurationIndex 21), aligned to the column list above.
            rows.append(f"    ({g['marker_spell']}, 192, 0, 0, 0, 101, 1, 21, 1, -1,"
                        f" 6, 1, 4, 0, 0, {g['spell_icon']}, 1, '{sql_escape(g['name'])}')")
    lines.append(',\n'.join(rows) + ';')

    entries = ', '.join(str(g['item_entry']) for g in glyphs)
    lines += [
        '',
        f'DELETE FROM `item_template` WHERE `entry` IN ({entries});',
        'INSERT INTO `item_template`',
        '    (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `BuyPrice`, `SellPrice`,',
        '     `InventoryType`, `AllowableClass`, `AllowableRace`, `ItemLevel`, `RequiredLevel`, `stackable`,',
        '     `bonding`, `description`, `spellid_1`, `spelltrigger_1`, `spellcharges_1`, `Material`) VALUES',
    ]
    rows = []
    for g in glyphs:
        rows.append(f"    ({g['item_entry']}, 16, 0, '{sql_escape(g['name'])}', {g['item_display']},"
                    f" 3, 0, 25000, 0, -1, -1, 60, 15, 1, 2,"
                    f" '', {g['apply_spell']}, 0, -1, -1)")
    lines.append(',\n'.join(rows) + ';')

    lines += [
        '',
        f"DELETE FROM `custom_glyphs` WHERE `glyph_id` IN ({', '.join(str(g['glyph_id']) for g in glyphs)});",
        'INSERT INTO `custom_glyphs` (`glyph_id`, `name`, `handler`, `handler_data`) VALUES',
    ]
    rows = [f"    ({g['glyph_id']}, '{sql_escape(g['name'])}', '{g['handler']}', '{g['handler_data']}')"
            for g in glyphs]
    lines.append(',\n'.join(rows) + ';')

    lines += [
        '',
        '-- Add to the shared glyph drop pool',
        f"DELETE FROM `reference_loot_template` WHERE `Entry` = 90001 AND `Item` IN ({entries});",
        'INSERT INTO `reference_loot_template` (`Entry`, `Item`, `Reference`, `Chance`, `QuestRequired`, `LootMode`, `GroupId`, `MinCount`, `MaxCount`, `Comment`) VALUES',
    ]
    rows = [f"    (90001, {g['item_entry']}, 0, 0, 0, 1, 1, 1, 1, 'Custom Glyph - {sql_escape(g['name'])}')"
            for g in glyphs]
    lines.append(',\n'.join(rows) + ';')

    emit_creature_sql(lines, 'creaturemodeldata_dbc', CMD_COLUMNS, CMD_FLOATS,
                      manifest.get('creature_model_data', []))
    emit_creature_sql(lines, 'creaturedisplayinfo_dbc', CDI_COLUMNS, CDI_FLOATS,
                      manifest.get('creature_display_info', []))
    lines.append('')

    Path(dest).write_text('\n'.join(lines))


# ============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dbc-src', required=True,
                    help='dir with the client-effective Item.dbc, Spell.dbc, ... '
                         '(use tools/extract_client_dbcs.py to produce it)')
    ap.add_argument('--hd-locale', metavar='LOCALE',
                    help='ALSO write wow-client/Data/<LOCALE>/patch-<LOCALE>-z.mpq '
                         'for HD repack clients whose own lettered patches outrank '
                         'patch-P (e.g. --hd-locale enUS). Deploy ONE archive only.')
    args = ap.parse_args()
    src = Path(args.dbc_src)

    glyphs = json.loads((MODULE / 'tools/client_patch_manifest.json').read_text())['glyphs']

    items = Dbc(src / 'native_Item.dbc' if (src / 'native_Item.dbc').exists() else src / 'Item.dbc')
    spells = Dbc(src / 'native_Spell.dbc' if (src / 'native_Spell.dbc').exists() else src / 'Spell.dbc')
    props = Dbc(src / 'native_GlyphProperties.dbc' if (src / 'native_GlyphProperties.dbc').exists() else src / 'GlyphProperties.dbc')
    shapeshifts = Dbc(src / 'native_SpellShapeshiftForm.dbc' if (src / 'native_SpellShapeshiftForm.dbc').exists() else src / 'SpellShapeshiftForm.dbc')

    # Set SHAPESHIFT_FLAG_STANCE (0x1) for Druid forms in SpellShapeshiftForm.dbc
    # to allow the client to cast any spell without auto-unshifting.
    DRUID_FORMS = {1, 3, 4, 5, 8} # Cat, Travel, Aqua, Bear, Dire Bear
    for i in range(shapeshifts.recs):
        offset = i * shapeshifts.recsize
        row = list(struct.unpack_from(f'<{shapeshifts.fields}i', shapeshifts.records, offset))
        form_id = row[0]
        if form_id in DRUID_FORMS:
            row[19] |= 1  # Field 19 is flags1
            struct.pack_into(f'<{shapeshifts.fields}i', shapeshifts.records, offset, *row)

    # Clear Druid form bits from StancesNot so no spell is blocked while
    # shapeshifted. 3.3.5 Spell.dbc stores Stances/StancesNot as 64-bit pairs:
    # Stances = fields 12-13, StancesNot = fields 14-15 (13/15 are always-zero
    # high words). Only field 14 is touched. Never OR Druid bits into Stances
    # (field 12): the client renders every Stances bit into the fixed-size
    # "Requires <form>, ..." tooltip line, and inflating ~1000 spells' masks
    # overflows that buffer -> silent heap corruption -> ERROR #132 on exit.
    # Casting-while-shifted is granted by SHAPESHIFT_FLAG_STANCE above instead.
    DRUID_FORM_MASK = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 7) | (1 << 30)
    for i in range(spells.recs):
        offset = i * spells.recsize
        row = list(struct.unpack_from(f'<{spells.fields}i', spells.records, offset))
        stances_not = row[14] & 0xFFFFFFFF
        if stances_not & DRUID_FORM_MASK:
            stances_not &= ~DRUID_FORM_MASK
            row[14] = stances_not if stances_not < 0x80000000 else stances_not - 0x100000000
            struct.pack_into(f'<{spells.fields}i', spells.records, offset, *row)

    apply_template = spells.get_record(APPLY_TEMPLATE_SPELL)
    marker_template = spells.get_record(MARKER_TEMPLATE_SPELL)
    item_template = items.get_record(ITEM_TEMPLATE_ENTRY)

    for g in glyphs:
        # Item.dbc: id, class, subclass, sound, material, display, invtype, sheathe
        row = list(item_template)
        row[0] = g['item_entry']
        row[5] = g['item_display']
        items.add_record(row)

        # Apply spell: clone native glyph apply, retarget the glyph property.
        row = list(apply_template)
        row[SPELL_ID_FIELD] = g['apply_spell']
        row[SPELL_MISCVALUE1_FIELD] = g['glyph_id']
        row[SPELL_ICON_FIELD] = g['spell_icon']
        row[SPELL_NAME_FIELD] = spells.add_string(g['name'])
        row[SPELL_DESC_FIELD] = spells.add_string(g['tooltip'])
        spells.add_record(row)

        # Marker aura (cosmetics): clone the beta dummy aura; its description is
        # what the glyph panel shows for the socketed glyph.
        if not g['effect_spell']:
            row = list(marker_template)
            row[SPELL_ID_FIELD] = g['marker_spell']
            row[SPELL_ICON_FIELD] = g['spell_icon']
            row[SPELL_NAME_FIELD] = spells.add_string(g['name'])
            row[SPELL_DESC_FIELD] = spells.add_string(g['tooltip'])
            spells.add_record(row)

        flags = 1 if g['type'] == 'minor' else 0
        props.add_record([g['glyph_id'], g['effect_spell'] or g['marker_spell'], flags, g['socket_icon']])

    # EverQuest-inspired custom active spells (separate manifest, optional).
    eq_pack_path = MODULE / 'tools/eq_spell_pack.json'
    eq_pack = json.loads(eq_pack_path.read_text()) if eq_pack_path.exists() else None
    if eq_pack:
        eq_base = spells.get_record(EQ_BASE_TEMPLATE)
        for spec in eq_pack['spells']:
            spells.add_record(build_eq_spell_row(spells, eq_base, spec))
        print(f"added {len(eq_pack['spells'])} EQ pack spells to Spell.dbc")

    # Passive talents that modify the EQ pack (separate manifest, optional).
    eq_talent_path = MODULE / 'tools/eq_talent_pack.json'
    eq_talent_pack = json.loads(eq_talent_path.read_text()) if eq_talent_path.exists() else None
    if eq_talent_pack:
        eq_base = spells.get_record(EQ_BASE_TEMPLATE)
        rows = build_eq_talents(spells, eq_base, eq_talent_pack)
        for row in rows:
            spells.add_record(row)
        print(f"added {len(rows)} EQ talent pack spells to Spell.dbc "
              f"({len(eq_talent_pack['talents'])} talents)")

    manifest = json.loads((MODULE / 'tools/client_patch_manifest.json').read_text())

    def append_manifest_rows(dbc, entries):
        for entry in entries:
            row = list(entry['row'])
            for j in entry['string_fields']:
                row[j] = dbc.add_string(row[j]) if row[j] else 0
            dbc.add_record(row)

    cmd = Dbc(src / 'native_CreatureModelData.dbc' if (src / 'native_CreatureModelData.dbc').exists() else src / 'CreatureModelData.dbc')
    cdi = Dbc(src / 'native_CreatureDisplayInfo.dbc' if (src / 'native_CreatureDisplayInfo.dbc').exists() else src / 'CreatureDisplayInfo.dbc')
    append_manifest_rows(cmd, manifest.get('creature_model_data', []))
    append_manifest_rows(cdi, manifest.get('creature_display_info', []))

    archive = {
        'DBFilesClient\\Item.dbc': items.dumps(),
        'DBFilesClient\\Spell.dbc': spells.dumps(),
        'DBFilesClient\\GlyphProperties.dbc': props.dumps(),
        'DBFilesClient\\CreatureModelData.dbc': cmd.dumps(),
        'DBFilesClient\\CreatureDisplayInfo.dbc': cdi.dumps(),
        'DBFilesClient\\SpellShapeshiftForm.dbc': shapeshifts.dumps(),
    }
    for md in manifest.get('model_dirs', []):
        src_dir = Path(md['src'])
        if not src_dir.is_absolute():
            src_dir = MODULE / src_dir
        if not src_dir.is_dir():
            # Loud, because a silently-missing model dir ships an archive that
            # drops custom creature models that were in the previous patch.
            print(f'WARNING: model_dir missing, skipping: {src_dir}')
            continue
        for p in sorted(src_dir.iterdir()):
            if p.is_file():
                archive[md['dest'] + '\\' + p.name] = p.read_bytes()

    # Verbatim files copied in as-is (custom DBCs that wholesale-replace native
    # ones, e.g. the custom-title CharTitles.dbc — formerly shipped as patch-P).
    for vf in manifest.get('verbatim_files', []):
        src = Path(vf['src'])
        if not src.is_absolute():
            src = MODULE / src
        archive[vf['dest']] = src.read_bytes()

    dest = MODULE / 'wow-client/Data/patch-P.mpq'
    write_mpq(dest, archive)
    print(f'wrote {dest} ({dest.stat().st_size} bytes)')

    # Optional locale override patch for HD repack clients: repacks ship their
    # own lettered patches (e.g. patch-enUS-s.mpq) that outrank patch-P, so a
    # locale patch with a higher letter is needed to win the override chain.
    if args.hd_locale:
        loc = args.hd_locale
        localized_dir = MODULE / 'wow-client/Data' / loc
        localized_dir.mkdir(parents=True, exist_ok=True)
        dest_loc = localized_dir / f'patch-{loc}-z.mpq'
        write_mpq(dest_loc, archive)
        print(f'wrote HD locale override to {dest_loc}')
        print()
        print(f'WARNING: deploy EXACTLY ONE archive per client — patch-{loc}-z.mpq for')
        print('the HD client it was built against, patch-P.mpq for native clients.')
        print('Mounting the same archive twice corrupts the 3.3.5 client heap and')
        print('crashes with ERROR #132 on exit.')


    # Write loose DBCs for server deployment (install.sh will copy these to the server)
    server_dbc_dir = MODULE / 'dbc'
    server_dbc_dir.mkdir(parents=True, exist_ok=True)
    (server_dbc_dir / 'Spell.dbc').write_bytes(spells.dumps())
    (server_dbc_dir / 'SpellShapeshiftForm.dbc').write_bytes(shapeshifts.dumps())
    print(f'wrote loose server DBCs to {server_dbc_dir}')

    sql_dest = MODULE / 'data/sql/db-world/25_custom_glyphs_client.sql'
    emit_sql(glyphs, manifest, sql_dest)
    print(f'wrote {sql_dest}')

    if eq_pack:
        eq_sql = MODULE / 'data/sql/db-world/28_eq_spell_pack.sql'
        emit_eq_spell_sql(eq_pack, eq_sql)
        print(f'wrote {eq_sql}')

    if eq_talent_pack:
        eq_talent_sql = MODULE / 'data/sql/db-world/30_eq_talent_pack.sql'
        emit_eq_talent_sql(eq_talent_pack, eq_talent_sql)
        print(f'wrote {eq_talent_sql}')


if __name__ == '__main__':
    main()
