#!/usr/bin/env python3
"""Reword the converted talents' client tooltips so they describe their new scope.

Phase 1d replaced class scoping on 198 talents with a school scope (Tier 1) or with
no scope at all (Tier 2), but the text the client shows still lives in `Spell.dbc`
and still names the abilities, spec or class the talent used to be limited to. The
talents' *behaviour* is settled; this tool settles what the tooltip says about it.

Two remedies, because the text is hand-written prose and a mechanical rewrite cannot
be trusted on every sentence:

  rewrite  the scope span is a plain list of spell names (or a "<spec> spells"
           phrase), so it can be replaced with the school phrase in place:
           "your Fireball, Frostfire Bolt and Scorch spells" -> "your Fire and Frost
           spells". Chosen whenever exactly one such span exists, so nothing else in
           the sentence can be touched by mistake.
  append   anything else keeps its original sentence - which stays *true*, since the
           spells it names are within the new scope - and gains one colour-coded line
           naming the scope it actually has now. This cannot break the grammar and
           cannot touch a `$s1` token.

A tooltip already naming exactly the new scope (Shadow Affinity says "your Shadow
spells" and is Shadow-scoped) is left alone: there is nothing to say.

Outputs:
    tools/talent_tooltip_overrides.json   one entry per rank spell
    docs/TALENT_TOOLTIPS.md               the review table (local, like other reports)

`--check` re-derives and fails if the committed JSON is stale. Entries with
"manual": true are never overwritten, so a hand-written line survives regeneration.
"""

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_client_patch import Dbc, SF_AURA, SF_DESC  # noqa: E402
from classify_talent_synergy import (  # noqa: E402
    CORE_ROOT, MANIFEST_PATH, build_family_index, classify_chains, dbc_string,
    derive_school_mask_auras, load_chains, load_spells, parse_enum, resolve_dbc)

import school_scope_tier1 as t1  # noqa: E402

MODULE = Path(__file__).resolve().parent.parent
SQL_DIR = MODULE / 'data/sql/db-world'
OVERRIDES_PATH = MODULE / 'tools/talent_tooltip_overrides.json'
REPORT_PATH = MODULE / 'docs/TALENT_TOOLTIPS.md'

TIER1_SQL = '34_school_scope_tier1.sql'
TIER2_SQL = '33_broad_talent_scoping.sql'

SCHOOL_NAMES = {1: "Physical", 2: "Holy", 4: "Fire", 8: "Nature",
                16: "Frost", 32: "Shadow", 64: "Arcane"}
UNIVERSAL_MASK = 0x7F

# The noun a run of spell names can be followed by. Kept as a small set: the run
# swallows whichever of these follows it, so the replacement supplies the noun and
# no fragment of the old one is left trailing. Singular forms are listed because
# Warrior/Rogue talents say "ability" ("your Heroic Strike ability").
NOUNS = r'spells?|abilities|ability|attacks?|effects?|damage|charges?'

MARKER_COLOR = '|cff1eff00'
MARKER = f"\n{MARKER_COLOR}SpellDraft: also affects %s.|r"


def scope_phrase(mask):
    """\"Fire and Frost\" / \"Physical\" / None - the human name for a school mask."""
    if mask == UNIVERSAL_MASK:
        return "all of your spells"
    names = [name for bit, name in SCHOOL_NAMES.items() if mask & bit]
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def scope_sentence(mask):
    """The phrase as it reads inside \"also affects ...\"."""
    phrase = scope_phrase(mask)
    if phrase is None:
        return None
    if phrase == "all of your spells":
        return phrase
    return f"your {phrase} spells"


def ids_from(path):
    text = path.read_text(encoding='utf-8')
    body = '\n'.join(l for l in text.split('\n') if not l.startswith('--'))
    match = re.search(r'DELETE FROM `spell_dbc` WHERE `ID` IN \(([^)]*)\);', body)
    return {int(x) for x in match.group(1).split(', ')}


def run_pattern(names):
    """A regex matching a maximal ', ' / ' and ' list of these spell names.

    Names that are the suffix of another name in the same list are dropped: the
    classmask's index contains both "Unstable Affliction" and "Affliction", and a
    suffix match would rewrite only the tail of the run, leaving "your Corruption and
    Unstable" in front of the replacement.
    """
    names = [n for n in names if not any(o != n and o.endswith(n) for o in names)]
    alt = '|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    node = rf'(?<![a-z])(?:{alt})(?![a-z])'
    sep = r'(?:\s*(?:,|and|or|/)\s*)'
    return re.compile(rf'{node}(?:{sep}{node})*', re.I)


def named_school_mask(text_lower):
    """Schools the text itself names, for the "already accurate" test."""
    mask = 0
    for word in re.split(r'[^a-z]+', text_lower):
        mask |= t1.SCHOOL_WORDS.get(word, 0)
    return mask


def load_t1_rewrites(path):
    """{spell_id: [(slot, aura, misc)]} for the rewritten slots in the Tier 1 SQL.

    Used to decide what a tooltip should claim when the derivation found no school in
    it: if every aura the talent *gained* is schoolless (MOD_DISPEL_RESIST), the effect
    really does apply to every spell and the tooltip may say so - rather than this tool
    guessing a scope the data does not support. Slots the conversion left alone (the
    native stun-duration aura on Stoicism, say) are not "gained" and are excluded.
    """
    text = path.read_text(encoding='utf-8')
    cols = re.search(r'INSERT INTO `spell_dbc`\n  \(([^)]*)\)', text).group(1)
    names = [c.strip().strip('`') for c in cols.split(',')]
    out = {}
    for match in re.finditer(r'^  \((\d+), (.*?)\),?;?$', text, re.M):
        values = match.group(2).split(', ')

        def val(column):
            return int(values[names.index(column) - 1])

        auras = []
        for slot, aura_column in enumerate(('EffectAura_1', 'EffectAura_2', 'EffectAura_3')):
            aura = val(aura_column)
            if aura:
                auras.append((slot, aura, val(f'EffectMiscValue_{slot + 1}')))
        out[int(match.group(1))] = auras
    return out


def build_entries(dbc, spells, index, results, tab_classes, rewrites):
    """{spell_id: entry} for every rank spell of every converted talent."""
    t1_ids, t2_ids = ids_from(SQL_DIR / TIER1_SQL), ids_from(SQL_DIR / TIER2_SQL)
    t1_talents = {r['talentId'] for r in t1.select_chains(results)[0]}
    t2_talents = {r['talentId'] for r in results
                  if set(r['ranks']) & t2_ids and r['talentId'] not in t1_talents}

    entries = {}
    for result in results:
        tier = 't1' if result['talentId'] in t1_talents else (
            't2' if result['talentId'] in t2_talents else None)
        if not tier:
            continue
        row = spells.get(result['ranks'][0])
        if not row:
            continue
        text = dbc_string(dbc, row[SF_DESC])
        if tier == 't1':
            mask, why = t1.derive_school(dbc, index, result, spells)
        else:
            mask, why = UNIVERSAL_MASK, "Tier 2: the class family was dropped"
        if mask:
            sentence = scope_sentence(mask)
        else:
            # No school in the tooltip. Claim "every spell" only when the conversion
            # itself was schoolless - otherwise there is nothing truthful to say.
            gained = [(aura, misc) for sid in result['ranks']
                      for slot, aura, misc in rewrites.get(sid, [])
                      if spells[sid][SF_AURA + slot] in (t1.ADD_FLAT_MODIFIER,
                                                         t1.ADD_PCT_MODIFIER)]
            sentence = (scope_sentence(UNIVERSAL_MASK)
                        if gained and all(a in t1.UNIVERSAL_AURAS for a, _ in gained)
                        else None)
        _, names = t1.named_spells(dbc, index, result, text.lower())
        for spell_id in result['ranks']:
            srow = spells.get(spell_id)
            if not srow:
                continue
            old = dbc_string(dbc, srow[SF_DESC])
            status, new, note = remedy(old, mask, names, tier, sentence)
            entries[spell_id] = {
                'talent_id': result['talentId'],
                'talent': result['name'],
                'class': tab_classes.get(result.get('tabId'), result['className']),
                'tier': tier,
                'scope': sentence,
                'status': status,
                'old': old,
                'new': new,
                'why': why,
            }
    return entries


def tooltip_is_accurate(text, mask, tier):
    """Does the description already describe the scope the talent now has?"""
    lowered = text.lower()
    if mask == UNIVERSAL_MASK:
        return any(phrase in lowered for phrase in t1.UNIVERSAL_PHRASES)
    # Every school the text names must be one of the schools the talent now covers,
    # and it must name all of them: "your Shadow spells" is accurate for Shadow,
    # but "your Frost spells" is not for Frost+Fire.
    return bool(mask) and named_school_mask(lowered) == mask


def remedy(old, mask, names, tier, sentence):
    """(status, new_text, note) for one rank spell's description."""
    if not old:
        return 'review', old, 'no description in Spell.dbc'
    if tooltip_is_accurate(old, mask, tier):
        return 'ok', old, 'already names the new scope'
    if sentence is None:
        return 'review', old, 'no school to name (healing, or unscoped)'
    if tier == 't2':
        sentence = "all of your spells"
    rewritten = try_rewrite(old, tier, names, sentence, mask)
    if rewritten:
        return 'rewrite', rewritten, 'scope span replaced in place'
    return 'append', old + (MARKER % sentence), 'kept the sentence, added a scope line'


def try_rewrite(old, tier, names, sentence, mask):
    """
    Replace the single scope span in `old`, or None if the sentence is not that shape.

    Only two shapes are rewritten, because both are one unambiguous span: a run of
    spell names ("your Fireball, Frostfire Bolt and Scorch spells") and a spec
    phrase ("your Destruction spells"). The span always swallows the noun that
    follows it, so the replacement supplies one - which is what stops a preceding
    "your" from doubling up. Anything else is left to the append remedy.
    """
    noun = NOUNS
    candidates = []

    if names:                                   # a run of spell names
        spans = list(run_pattern(names).finditer(old))
        if len(spans) == 1:
            candidates.append(spans[0])

    if tier == 't1':                            # a spec phrase: "your Destruction spells"
        for spec, spec_mask in t1.SPEC_SCHOOLS.items():
            if not spec_mask or (spec_mask & ~mask):    # only if it widens to `mask`
                continue
            # The leading "your" is required, not optional: spec names are also
            # spell-name fragments ("Unstable Affliction"), and matching one of those
            # would rewrite the tail of a spell name. Every spec scope in the data is
            # written as "your <spec> spells", so anchoring on "your" is exact, and
            # the span then includes that "your" so the replacement does not double it.
            pattern = re.compile(rf'(?i)(?<![a-z])your\s+{re.escape(spec)}(?![a-z])'
                                 rf'(?:\s+(?:{noun}))?')
            spans = list(pattern.finditer(old))
            if len(spans) == 1:
                candidates.append(spans[0])
            break

    if len(candidates) != 1:
        return None

    span = candidates[0]
    start, end = extend_span(old, span.start(), span.end(), noun)
    if partial_run(old, start, end, names):
        return None
    original = old[start:end]
    if '$' in original:                         # never touch a substitution token
        return None
    new = old[:start] + sentence + old[end:]
    if new == old or not new.strip():
        return None
    # The tooltip's numbers live in the `$` tokens; replacing text must not disturb
    # them, or the tooltip silently loses a value.
    if sorted(re.findall(r'\$[a-zA-Z0-9:/;]*', new)) != sorted(
            re.findall(r'\$[a-zA-Z0-9:/;]*', old)):
        return None
    return new


def partial_run(old, start, end, names):
    """
    Is the matched span only part of the sentence's name run?

    Spell names can contain another name as a suffix - "Unstable Affliction" and
    "Affliction" are both spells - so the pattern can start matching mid-run and leave
    a fragment ("your Corruption and Unstable" + the replacement). If the text either
    side of the span continues the run through a separator, the match is not the whole
    scope and the rewrite is refused; the append remedy still tells the truth.
    """
    if not names:
        return False
    alt = '|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    name = rf'(?<![a-z])(?:{alt})(?![a-z])'
    sep = r'\s*(?:,|and|or|/)\s*'
    # The list continues to the left of the span: the sentence names spells the
    # classmask does not cover (Pandemic's "Corruption and Unstable Affliction",
    # where only the second is a mask member), so replacing this span would leave
    # "Corruption and Unstable" stranded in front of the replacement.
    if re.search(rf'(?i){sep}$', old[:start]):
        return True
    before = re.search(rf'(?i){name}{sep}$', old[:start])
    after = re.match(rf'(?i){sep}{name}', old[end:])
    return bool(before or after)


def extend_span(old, start, end, noun):
    """
    Widen a matched span to the whole scope phrase around it.

    The scope is what the sentence says the player owns, so the span has to take the
    "your" in front of it ("while casting Arcane Missiles" has none, "of your
    Bloodthirst" does) and the noun behind it ("spells"/"ability"/"abilities").
    Taking the noun is what stops a leftover "ability" from trailing the replacement,
    and taking the "your" is what stops "your your Fire spells".
    """
    left = re.search(r'(?i)(your\s*)$', old[:start])
    if left:
        start = left.start()
    right = re.match(rf'(?i)\s+(?:{noun})\b', old[end:])
    if right:
        end += right.end()
    return start, end


def load_manual(path):
    """Entries a human has finished with, keyed by spell id."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    return {int(k): v for k, v in data.get('spells', {}).items() if v.get('manual')}


def merge(entries, manual):
    for spell_id, entry in manual.items():
        entries[spell_id] = entry
    return entries


def render_report(entries):
    """Markdown: what each affected tooltip will say, old -> new."""
    counts = collections.Counter(e['status'] for e in entries.values())
    talents = len({e['talent_id'] for e in entries.values()})
    lines = [f"# Talent tooltips after the Phase 1d rewrite", "",
             f"{len(entries)} rank spells across {talents} talents.", "",
             "| status | spells | what it does |", "|---|---:|---|",
             f"| `ok` | {counts['ok']} | already names the new scope - no change |",
             f"| `rewrite` | {counts['rewrite']} | scope span replaced in place |",
             f"| `append` | {counts['append']} | sentence kept, one scope line added |",
             f"| `review` | {counts['review']} | nothing safe to compose - needs a human |",
             ""]
    by_status = collections.defaultdict(list)
    for entry in entries.values():
        by_status[entry['status']].append(entry)
    for status, heading in (('review', '## Needs a human'),
                            ('rewrite', '## Rewritten in place'),
                            ('append', '## Sentence kept, a scope line added'),
                            ('ok', '## Already accurate')):
        group = sorted(by_status[status], key=lambda e: (e['class'], e['talent']))
        if not group:
            continue
        lines += [heading, ""]
        seen = set()
        for entry in group:
            key = (entry['talent_id'], entry['old'], entry['new'])
            if key in seen:                     # one line per talent, not per rank
                continue
            seen.add(key)
            lines += [f"### {entry['class']} - {entry['talent']} "
                      f"(`{entry['tier']}`, scope: {entry['scope']})", "",
                      f"- now: `{entry['old']}`",
                      f"- new: `{entry['new']}`", ""]
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dbc', help='Spell.dbc (default: resolve_dbc)')
    ap.add_argument('--print', action='store_true', help='dump every proposal')
    ap.add_argument('--check', action='store_true', help='fail if the JSON is stale')
    args = ap.parse_args()

    dbc_path = resolve_dbc(args.dbc)
    dbc = Dbc(dbc_path)
    manifest = json.load(open(MANIFEST_PATH, encoding='utf-8'))
    tab_classes = {t['tabId']: t['class'].capitalize() for t in manifest['tabs']}
    chains = load_chains(None)
    wanted = {s for _, _, _, r in chains for s in r}
    _, spells = load_spells(dbc_path, wanted)
    auras = parse_enum(os.path.join(CORE_ROOT, 'game/Spells/Auras/SpellAuraDefines.h'),
                       ['SPELL_AURA_'])
    results = classify_chains(chains, dbc, spells, auras, derive_school_mask_auras(),
                              tab_classes)
    index = build_family_index(dbc)

    entries = merge(build_entries(dbc, spells, index, results, tab_classes,
                                   load_t1_rewrites(SQL_DIR / TIER1_SQL)),
                    load_manual(OVERRIDES_PATH))
    counts = collections.Counter(e['status'] for e in entries.values())
    print(f"{len(entries)} rank spells, "
          f"{len({e['talent_id'] for e in entries.values()})} talents")
    print('  '.join(f'{k}={v}' for k, v in sorted(counts.items())))

    if args.print:
        for spell_id, entry in sorted(entries.items()):
            print(f"\n[{entry['status']}] {spell_id} {entry['class']} {entry['talent']}")
            print(f"  old: {entry['old']}")
            print(f"  new: {entry['new']}")

    if args.check:
        if not OVERRIDES_PATH.exists():
            print('missing tools/talent_tooltip_overrides.json', file=sys.stderr)
            return 1
        committed = {int(k): v for k, v in
                     json.loads(OVERRIDES_PATH.read_text(encoding='utf-8'))['spells'].items()}
        stale = [sid for sid, entry in entries.items()
                 if sid not in committed or (not committed[sid].get('manual')
                                             and committed[sid] != entry)]
        if stale:
            print(f'{len(stale)} stale entries, regenerate: {stale[:5]}', file=sys.stderr)
            return 1
        print(f'overrides up to date: {len(committed)} entries')
        return 0

    payload = {
        'generated_by': 'tools/reword_talent_tooltips.py',
        'note': 'Applied to the client Spell.dbc by tools/build_client_patch.py. '
                'Set "manual": true on an entry to keep a hand-written "new".',
        'spells': {str(k): entries[k] for k in sorted(entries)},
    }
    OVERRIDES_PATH.write_text(json.dumps(payload, indent=1) + '\n', encoding='utf-8')
    REPORT_PATH.write_text(render_report(entries), encoding='utf-8')
    print(f'wrote {OVERRIDES_PATH.relative_to(MODULE)} and '
          f'{REPORT_PATH.relative_to(MODULE)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())