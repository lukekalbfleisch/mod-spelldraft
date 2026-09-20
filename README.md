# mod-spelldraft
**Classless-ish Randomized Spell Draft Mode for AzerothCore (3.3.5a)**

`mod-spelldraft` is a custom game mode that transforms the standard World of Warcraft leveling experience into a randomized, classless ability draft. 

Designed primarily for players who want a fun, rogue-like draft experience on their private server, this module removes traditional class boundaries while maintaining race and class identity:
*   **Race & Class Identity:** You still pick a starting race and class, receiving their native starting stats, class quests, and base attributes.
*   **Universal Quests:** All class-restricted quests are unlocked, allowing any class to complete any other class's quest chain (such as the Warrior's Whirlwind weapon quest or the Warlock's pet summon quests).
*   **Ability Drafting as You Level:** Every level-up intercepts standard progression and prompts you with a choice of 3 randomized active spells.
*   **Tomes and Scrolls in the World:** Defeating enemies gives you a chance to loot custom items to customize your build:
    *   *Scrolls of Reroll/Ban:* Prune or roll again on your active ability draft choices.
    *   *Lost Grimoires:* Trigger a bonus active spell draft at any time.
    *   *Tomes of Talents:* Draft custom passive talents (like *Cruelty*, *Ignite*, or *Conviction*) from any class. Access your drafted talents and spells by typing `/spelldraft` in the game chat.
*   **Universal Gear & Weapon Proficiencies:** Any character can equip any armor type (Cloth to Plate) and wield any weapon type, with weapon skills training automatically to the level cap on login.
*   **Automatic Spell Ranking:** No need to visit class trainers. Drafted spells automatically upgrade to their highest available rank as you level up.
*   **Mystic Enchants (Random Loot Enchantments):** Gear of Uncommon quality or better has a chance to roll unique bonuses when looted, crafted, or won. These enchants grant passive glyph-tier effects, combat proc recipes (such as cross-class spell triggers), or cosmetic shapeshift overrides, and can be rerolled, imbued, or transferred via Nibbs the Imp.
*   **Prestige System:** Reach level 80 and reset back to level 1 (or level 55 for Death Knights) with a prestige title. While spells and talents are wiped on reset, you earn **Prestige Tokens** (10 per reset) and starting bonus rerolls for your next run.
*   **Prestige Rewards Shop:** Access a custom, tabbed reward shop within your Grimoire interface (`/spelldraft` menu, click the Gold Purse icon next to the Prestige label) to purchase rare mounts, vanity companion pets, account-bound heirloom weapons and armor (+XP scaling), scrolls, and transformation toys using your Prestige Tokens.

---

## Player Connection Guide (Client-Only)

If you are a player connecting to a server running SpellDraft, you do **not** need to install or build the server module. You only need the client files:
1. Go to the **Releases** section of this repository and download the latest `wow-client.zip`.
2. Extract the zip file, copy the `Interface/` folder into your World of Warcraft game directory, and copy `Data/patch-P.mpq` into your client's `Data/` folder.
   * The shipped `patch-P.mpq` is built for the **native (unmodified) WotLK 3.3.5a client**.
   * **HD / custom repack clients**: do **not** use the shipped archive — it would override your repack's databases with vanilla data (broken/green models, altered tooltips). A patch must be compiled against your specific repack; see [Building Client Patches for HD Repacks](#building-client-patches-for-hd-repacks) (usually your server owner provides this build).
   * ⚠️ Install exactly **one** SpellDraft patch archive. Mounting the same archive twice (e.g. as both `patch-P.mpq` and a locale patch) silently corrupts the 3.3.5 client's memory and crashes with `ERROR #132` on every exit.
3. **Fully close and relaunch the game** after copying — custom `.mpq` patches only load at client startup, not on `/reload`.

---

## Requirements & Dependencies

Before installing, ensure your server meets the following external dependencies:

*   **AzerothCore WotLK (3.3.5a)**: Compiles and runs against the AzerothCore master branch.
*   **[mod-ale (Eluna Lua Engine)](https://github.com/azerothcore/mod-ale) — REQUIRED**: This module depends on the Eluna scripting engine to run gameplay logic. Standard/classic Eluna forks do not support the required event hooks—use the official AzerothCore `mod-ale` module.
*   **mod-playerbots — Optional**: Fully supported. Playerbots are automatically skipped by the drafting system and will function as normal classes without any conflict.
*   **[mod-multiclass-summons](https://github.com/bdodroid/mod-multiclass-summons) — Optional**: Fully supported. Integrates out of the box to allow any class to control and use summon spells (like ghouls, demons, and elementals) with working pet bars and controls, bypassing default class restrictions.

---

## Spell Draft & Gear Rules

### 1. Universal Proficiencies
To support multi-class build paths (e.g. a Rogue who drafts Warrior abilities), characters are automatically granted:
*   **Armor**: Cloth, Leather, Mail, and Plate Mail.
*   **Weapons**: All weapon types (Swords, Axes, Maces, Polearms, Staves, Daggers, Fist Weapons, Bows, Crossbows, Guns, Thrown, Wands) and Shield Block.

### 2. Spell Draft Prerequisites & Class Locks
Spells are filtered server-side to ensure players are never offered useless cards:
*   **Death Knight Rune Spells**: Locked to the Death Knight class (Class 6) due to engine limitations on rune resources. Spells requiring only Runic Power remain draftable by anyone.
*   **Stance & Form Requirements**: Stance/form-specific spells (like Shred, Intercept, Shield Slam) will not appear in the draft pool until the prerequisite form/stance is learned.

### 3. Stance/Form Starter Kits
Drafting a stance or form auto-grants basic spells so you can immediately fight:
*   **Cat Form (768)**: Claw (1082), Prowl (5215)
*   **Bear Form (5487/9634)**: Maul (6807), Demoralizing Roar (99)
*   **Battle Stance (2457)**: Charge (100)
*   **Defensive Stance (71)**: Taunt (355)
*   **Berserker Stance (2458)**: Pummel (6552)

### 4. Consumable Draft Items
To facilitate draft customization and progression during leveling, enemies drop specialized scrolls and books that can be consumed out of combat:
*   **Scroll of Reroll**: Consuming this scroll grants the player **+1 Draft Reroll** token.
*   **Scroll of Ban**: Consuming this scroll grants the player **+1 Draft Ban** token.
*   **Lost Grimoire**: Consuming this grimoire immediately opens a bonus active spell draft choice.
*   **Tome of Talents**: Consuming this tome opens a draft selection screen allowing you to choose one passive talent from any class matching your level.

These items drop from normal enemies throughout the world, with dungeon and raid bosses having a significantly increased chance to drop them.

---

## Mystic Enchants (Random Loot Enchantments)

Weapons and armor of Uncommon quality or better that you **loot, craft, or win** have a chance to roll a **Mystic Enchant** — a bonus effect bound to that specific item, shown as an extra line on its tooltip:
*   **Glyph-tier enchants** grant a passive glyph effect while the item is equipped.
*   **Proc enchants** trigger cross-class effects in combat (e.g. Fireball casts hurling a free Fire Blast).
*   **Form enchants** change your shapeshift appearance (e.g. Bear Form becoming the spirit bear Arcturis).

Visit **Nibbs the Imp** and choose *Open Mystic Enchant services* for the enchanting window:
*   **Reroll / Imbue** — drag an item into the slot and pay gold to reroll its enchant, or to add one to an un-enchanted item.
*   **Reroll / Imbue (Epic+)** — spend a **Prestige Token** for a guaranteed **Epic-or-better** enchant.
*   **Transfer** — pay gold (scaling with the enchant's rarity) to move an enchant from one item to another. Overwriting the destination's enchant asks for confirmation; the source keeps a spent marker.

## Cosmetic & Custom Glyphs

Rare world drops include **glyphs that socket through the standard Glyphs panel** (talent window, level 15+):
*   **Minor cosmetic glyphs** change a shapeshift form's appearance: *White Bear, Black Bear, Red Lynx, Forest Lynx, Black Wolf* (Blizzard's scrapped beta glyphs, restored) and *Glyph of the Orca* (aquatic form).
*   **Major effect glyphs** add new combat effects, such as *Glyph of the Zealot* (melee strikes can unleash an Exorcism).

Any creature can rarely drop one (bosses far more often), and three **Forgotten Grimoire** tomes hidden in remote corners of Azeroth and Northrend each hold a guaranteed random glyph for explorers who find them.

---

## Game Modes

`GAME_MODE` in `lua_scripts/spelldraft_config.lua` decides what a **brand-new**
character starts as. Existing characters are never converted — each one keeps the
`prestige_stats.draft_state` it already has.

| Mode | A new character starts | Talent access | Spellbook |
| :--- | :--- | :--- | :--- |
| `traditional` *(default)* | With the class it was created with, **out of draft** (`draft_state = 0`) | The Grimoire lists the primary class's tree **plus a second class's** tree — pick one at Chromie or with `.multiclass` — funded by 1 point per level | The class opener set, then whatever the class trainer teaches |
| `draft` | **Classless**, drafting immediately (`draft_state = 1`) | Any class's talents, plus Tome of Talents drafts | Drafted from the active-spell pool |

In both modes the module grants the character's racial abilities and its class
opener set on first login, because this server ships an empty
`playercreateinfo_spell_custom` table (character creation hands out no spells),
and both modes can open the Grimoire with `/spelldraft`: the point pool lives in
`prestige_stats.talent_points` and grows by one point per level either way.

Drafting stays available under `traditional`: Chromie's prestige menu offers both
**Prestige (stay with my classes)** and **Prestige into Draft Mode**, and ending a
draft run restores the character's own class afterwards.

---

## Talent Points & Passive Progression

To give you more control over your character's build, `mod-spelldraft` features a custom Talent Point system alongside the active spell drafting:

*   **Earning Talent Points:** You earn **1 Talent Point per level-up** (from level 2 to 80). Death Knights are granted **54 Talent Points** on character creation (at level 55) to catch up.
*   **Purchasing Passives:** Open your Grimoire (type `/spelldraft` or click the *Grimoire* button on your talent frame) and and there you will find the **Talents** section. You can click on any unlocked passive talent from any class to purchase it using your points. Under `GAME_MODE = "traditional"` the list is narrowed to your own class trees — the primary class plus the second class you picked — while draft mode keeps every class available.
*   **Locked Talents (Draft-Only):** Active abilities, shapeshift forms, and playstyle-defining passive talents (like *Titan's Grip*, *Metamorphosis*, or *Tree of Life*) are **locked** (marked with a lock icon in the UI). These **cannot** be purchased with points and must be rolled and drafted from a **Tome of Talents** (drops chance from enemies and Bosses).
*   **Respecs:** If you wish to change your build, talk to **Nibbs the Imp** in starter zones or capital cities. He will reset all manually purchased talents and refund all spent points for free. Spells and talents you obtained through drafts are locked in and will not be touched by respecs.

**A second, independent talent route exists if `mod-multiclass` is also installed.**
Its `MulticlassTalents` client addon (`/mct`) spends the *native* talent point pool
(`Player::LearnTalent`, scaled by `Multiclass.TalentPointMultiplier`) instead of this
module's `prestige_stats.talent_points` counter — the two do not share a currency,
so a character with both modules running effectively has two separate talent
budgets to spend across the same classes. Pick one as the traditional-mode default
if you run both; the Grimoire is unaffected either way and keeps working exactly as
described above for draft mode.

---

## Talent Scoping (why talents are not class-limited)

Stock talents whose effect was scoped to a whole class ("your Arcane spells", "your
Fire spells") are broadened so a character's second class benefits too. That is
`data/sql/db-world/33_broad_talent_scoping.sql`, generated by
`tools/broaden_talent_scoping.py`: it writes a `spell_dbc` override per affected spell
with `SpellClassSet = 0`, which makes the engine stop matching the talent's
`EffectSpellClassMask` against the caster's class — `SpellInfo::IsAffected` returns true
on a zero family *before* it reads the mask.

**What changed: 56 talents / 151 spells** — the talents whose spellmod uses a cooldown,
cast time, duration, range or charge op and whose classmask covered more than one spell.
Those ops have no per-school aura lever, so the only options were "universal" or
"class-locked".

A second batch covers the talents that use an op *with* a per-school lever
(`data/sql/db-world/34_school_scope_tier1.sql`, generated by
`tools/school_scope_tier1.py`): **138 talents / 439 spells**. Their class scoping is
replaced by a *school* scope — or, where the tooltip already says "all spells"/"all
abilities", by every school, which is what those talents always meant:

| SpellModOp | per-school aura |
|---|---|
| `DAMAGE`, `DOT` | `MOD_DAMAGE_PERCENT_DONE` (or `MOD_HEALING_DONE_PERCENT` for the healing side) |
| `CRITICAL_CHANCE` | `MOD_SPELL_CRIT_CHANCE_SCHOOL` |
| `CRIT_DAMAGE_BONUS` | `MOD_CRIT_DAMAGE_BONUS` |
| `RESIST_MISS_CHANCE` | `MOD_INCREASES_SPELL_PCT_TO_HIT` |
| `RESIST_DISPEL_CHANCE` | `MOD_DISPEL_RESIST` (schoolless; covers offensive dispels) |
| `COST` (flat / pct) | `MOD_POWER_COST_SCHOOL` / `MOD_POWER_COST_SCHOOL_PCT` |
| `THREAT` (pct) | `MOD_THREAT` |

Each lever was verified against its consumer in this core (`SpellPctDamageModsDone`,
`GetTotalAuraModifierByMiscMask`, `SpellInfo::CalcPowerCost`) rather than assumed, and the
magnitudes transfer 1:1 because both sides use the same units. `THREAT` needs that check
spelled out, because its two forms are *not* interchangeable: the **pct** form is consumed
as `threat * (1 + value/100)` in `ApplySpellMod` and `MOD_THREAT` as
`threat * (100 + amount)/100` via `GetTotalAuraMultiplierByMiscMask`, so `-8` becomes `-8%`
either way — and Blizzard's own data proves it, since Silent Resolve carries the same `-7`
as both `aura=10 misc=66 amount=-7` and `aura=108 misc=2 amount=-7`, and Burning Soul's
`misc=4 (Fire) amount=-10` matches its tooltip's "reduced by 10%". The **flat** form is in
centi-threat units (`ApplySpellMod` divides it by 100, "in packets we send threat * 100"),
so it has no percentage aura that can stand in for it and is reported as a skip rather than
guessed. None of the converted chains use the flat form.

A slot that collapses onto the same (aura, school) pair keeps the **strongest** amount, not
the sum. Blizzard writes one bonus as several channel-specific mods — `Fire Power` is
`DAMAGE 2%` *and* `DOT 2%`, `Darkness` is `DAMAGE [2,2]` plus `DOT [2]` — which are
parallel channels of a single "+2%", so summing them would have made those talents two to
three times too strong (`Darkness` at 6% instead of 2%). Merging is still required, because
the engine *multiplies* matching auras, so two copies would double-dip. An intent that
needs a second aura (a "damage *and* healing" talent) takes a free effect slot, and the
chain is reported instead if the spell has none left.

The **school** cannot come from the data — expanding a classmask yields a median of 19
spells whose schools union to five or six different ones, and the talent's own
`SchoolMask` is `Physical` for all but five. So it is derived from Blizzard's own wording,
in priority order: the affected spells named in the tooltip ("your Backstab, Mutilate,
Garrote and Ambush" → Physical), a spec name ("your Destruction spells" → its schools),
a school named in it ("of your Arcane spells" → Arcane), or an explicit "all spells" /
"your instant spells" → every school. A named spell can appear with more than one school, and
those two reasons cannot be separated from the data: `Holy Fire` is Holy in 44 rows and Fire in
32 because its direct damage and its DoT are separate spells, while `Cone of Cold` is Frost in
54 rows and Nature in 3 because an NPC-only variant sits in the same family with a different
school. Narrowing to the majority would drop the DoT from the first case (`Searing Light` has to
keep reaching it) and any threshold separating 33% from 40% would be fitted to those six chains,
so the union stands — it errs *wider*, the direction the policy wants — and
`tools/school_scope_tier1.py --report` lists all six as a review section with the row counts, so
the extra school is visible rather than silent.

The **side** comes from the tooltip too, because a talent's `DAMAGE`/`DOT` mod covers both
damage and healing (Blizzard used the same lever for "+healing%"): "increases the amount
healed by your Renew" gets `MOD_HEALING_DONE_PERCENT` instead of a damage aura, "increases
the damage *and* healing" gets both, and everything else (crit, cost, hit) needs no side
split because those auras already apply to heals. That is what the earlier "hybrid"
review flag was for — it fires whenever a classmask merely *touches* a healing spell
("the damage of Blood Strike" is flagged hybrid because Death Strike heals itself), so the
tooltip, not the mask, decides.

**Every op that has a school lever is converted** — that is the whole Tier 1 bucket, 138
chains / 439 spells, including `THREAT`. What is left is 156 `needs-redesign` chains, and
**129 of them are spell-scoped, which the policy allows** ("your fireball does more damage"
is one of its own examples), so they are not violations and need nothing:

| bucket | chains | disposition |
|---|---:|---|
| class-wide Tier 3 (multi-bit mask) | 27 | **left class-locked** (decision, below) |
| spell-scoped, one op has a lever | 20 | leave |
| spell-scoped, no lever at all | 109 | leave |

Deliberately **not** broadened, with the reason:

- **Spell-scoped talents** (129). Their classmask keys on a specific spell (`Improved
  Fireball`, `Good Revenge`, `Brambles`) and the policy permits that scope, so they stay
  what their tooltips say. The 20 that do have a lever on *one* op stay too, for the same
  reason the Tier 2 policy left the single-spell talents alone: converting "Good Revenge"
  (+30% damage to Revenge) would make it "+30% damage to every Physical spell", turning a
  niche talent into a global buff. There is no lever at all for the other 109.
- **The 27 class-wide Tier 3 chains** — the only class-scoped talents left, kept as-is by
  decision. Their binding op scales an effect's **value**
  (`Unit::ApplyEffectModifiers` applies `ALL_EFFECTS`/`EFFECT1-3` to it, `BONUS_MULTIPLIER`
  to a spellpower coefficient), so dropping the family — the Tier 2 treatment — would
  multiply *every* spell's effect instead of widening a cooldown or a range. Fixing them
  means choosing a replacement effect by hand, one design call per talent, so they are
  recorded as a bounded tail (27 of 921 chains) rather than converted; a pairing still gets
  that tree's other talents. `--breakdown` lists all 27 with their blocking op.

`python3 tools/classify_talent_synergy.py --breakdown` writes that state locally
(`docs/TALENT_REDESIGN_PLAN.md`), and `--apply-spell-dbc` makes either report reflect what
the server actually loads. Both generators have a `--check` mode that verifies their SQL is
applied.

To see what actually changed, rather than read a 200-column diff:
`python3 tools/report_talent_changes.py` writes `docs/TALENT_CHANGES.md` (local, like the
other reports) with a per-class summary and one plain-language line per talent —
"`DAMAGE mod +10 (pct)` → `+10% damage for Physical spells`". It reads both sides from the
running stack and self-checks that every other column of every override is identical to
`Spell.dbc`, so a generator bug that moved an unrelated field cannot pass unnoticed.

**Tooltips** are reworded from the same analysis: `tools/reword_talent_tooltips.py` writes
`tools/talent_tooltip_overrides.json`, and `tools/build_client_patch.py` applies it to the
client `Spell.dbc` (field `Description`, 170 — the one the spell/talent tooltip is built
from; `ToolTip`, 187, is the aura text and is empty here). It has three outcomes per
tooltip, because the text is hand-written prose and a mechanical rewrite cannot be trusted
on every sentence:

| outcome | spells | what it does |
|---|---:|---|
| `rewrite` | 217 | one unambiguous scope span replaced in place — "your Fireball, Frostfire Bolt and Scorch spells" → "your Fire and Frost spells" |
| `append` | 222 | sentence kept (it stays true — the spells it names are in the new scope) plus one colour-coded line naming the scope it now has |
| `ok` | 151 | already names the new scope (Shadow Affinity says "your Shadow spells") — untouched |

A rewrite is refused, and the append used instead, whenever the span is not the whole scope
phrase: a list that continues past the span, a name that is the suffix of a longer name
("Unstable Affliction" vs "Affliction"), a span containing a `$` token, or a tooltip whose
`$` tokens would change. That last guard matters — the numbers in a tooltip live in those
tokens, so a reword that dropped one would silently delete a value. The reworder has a
`--check` mode, and `docs/TALENT_TOOLTIPS.md` (local) lists every old → new pair for review;
setting `"manual": true` on an entry keeps a hand-written line through regeneration.

Rebuilding the archive needs the DBCs your client actually uses, so it is a two-step:

```bash
python3 tools/extract_client_dbcs.py "/path/to/wow 3.3.5a client" /tmp/native_dbcs
python3 tools/build_client_patch.py --dbc-src /tmp/native_dbcs
```

Do **not** build from the server's `data/dbc` or from this repo's `dbc/`: those are this
module's *patched* output (they already carry the EQ pack spells), so building from them
would double-apply the patch and would not see a repack's own Spell.dbc. The build prints
the number of rewords it applied and warns if they did not match the text in the DBC it was
given — that means it was pointed at a different (repack) file and the tooltips in it were
replaced with ours.

---

## Death Knight Progression & Rules

Because Death Knights are a hero class and start at a higher level, the drafting system adapts to accommodate their progression:

*   **Starting State:** Upon character creation, a Death Knight starts at level 55, is granted all the standard native Death Knight starting abilities (Death Coil, Death Grip, Icy Touch, Plague Strike, Blood Strike, Blood Presence, Frost Presence, Death Gate, Runeforging, and the Acherus Deathcharger mount), and is immediately granted **5 spell drafts** to build their initial loadout.
*   **Drafts per Level:** Instead of 1 draft per level, Death Knights gain **3 active spell drafts per level-up** from level 56 to 80 to ensure they catch up with the spell counts of other classes.

---

## How Prestige Works

Once you reach the maximum level (80), you can visit the prestige NPC (Chromie) to prestige. The rules vary depending on your class type:

### Standard Classes
1.  **Level Reset:** Resets character level back to level 1.
2.  **Asset Mailbox Recovery:** Removes all your equipped gear and bags and mails them back to you so your inventory isn't lost.
3.  **Wipes Progress:** Clears all learned spells, active talents, quest histories, and action bars.
4.  **Scaling Rerolls & Bans:** Increases your prestige rank, grants a custom in-game title, and increases your starting rerolls/bans pool and rerolls per level-up for your next run.

### Death Knights
1.  **Level Reset:** Resets character level back to level 55.
2.  **Capital Gates Spawn:** Instead of starting back in the Ebon Hold starting zone, they spawn directly at the gates of their faction's capital city (Stormwind Gates for Alliance, Orgrimmar Gates for Horde).
3.  **Walk of Shame Quest:** Automatically accepts the final quest of the Death Knight starting chain ("Where Kings Walk" for Alliance, "Warchief's Blessing" for Horde) to integrate cleanly into the world.
4.  **Starting Spells:** Re-grants all the native starting Death Knight abilities (Death Coil, Death Grip, mount, Runeforging, etc.).
5.  **Asset Mailbox Recovery:** Removes all equipped gear and mails them back.
6.  **Wipes Progress:** Clears all drafted spells, active talents, quest histories, and action bars.
7.  **Catch-Up Mechanics:** Starts the next run with 5 drafts immediately, and gains 3 drafts per level-up from level 56 onwards.

---

## Step-by-Step Installation Instructions

### Option A: Automated Installation (Recommended)
We provide an automated script that performs all server-side staging, configuration, DBC deployment, and C++ Docker image rebuilding.

> **Docker users:** run the script with your container engine reachable (Docker Desktop started / `dockerd` running) and after the server has been brought up at least once (`docker compose up -d`) — the DBC deploy copies into the existing server containers, which works on Windows/macOS/Linux alike. If the script can't find them it prints the exact manual command to run.

1. Clone or copy `mod-spelldraft` into your server's `/modules/` folder:
   ```bash
   git clone <repo_url> modules/mod-spelldraft
   ```
2. Run the server installer script:
   ```bash
   cd modules/mod-spelldraft
   ./install.sh
   ```
 3. **Install Client files:** Copy `wow-client/Interface/AddOns/SpellDraft` into your client's `Interface/AddOns/`, and copy `wow-client/Data/patch-P.mpq` into your client's `Data/` folder (native 3.3.5a clients; HD repack users must compile their own patch — see the HD section). Install exactly **one** SpellDraft archive per client — mounting the same archive twice corrupts the client heap and crashes with `ERROR #132` on every exit.
 4. Restart your server!

---

<details>
<summary><b>Option B: Manual Installation (Step-by-Step) - Click to expand</b></summary>

If you prefer to perform the steps yourself, follow this sequence:

1. **Place the module:** Clone or copy `mod-spelldraft` into your server's `/modules/` directory.
2. **Stage Lua scripts:** Copy the config and script files into your server's Lua scripts directory:
   ```bash
   mkdir -p ../../env/dist/etc/modules/lua_scripts/SpellDraft
   cp lua/spelldraft_config.lua ../../env/dist/etc/modules/lua_scripts/
   cp -r lua/SpellDraft/* ../../env/dist/etc/modules/lua_scripts/SpellDraft/
   ```
3. **Copy config:** Copy `conf/mod_spelldraft.conf.dist` to `../../env/dist/etc/modules/mod_spelldraft.conf`.
 4. **Deploy DBC files:** Copy the module's server DBCs (`dbc/*.dbc`, e.g. `Spell.dbc` and `SpellShapeshiftForm.dbc`) into your server's runtime DBC directory:
    * **Docker/Podman (all platforms, incl. Windows Docker Desktop):** copy through the engine into the client-data container — the DBC folder lives inside a named volume that is usually *not* visible on your host filesystem, and the worldserver mounts it read-only:
      ```bash
      docker cp dbc/. ac-client-data-init:/azerothcore/env/dist/data/dbc/
      ```
      (Container names may vary — find yours with `docker ps -a --format '{{.Names}}' | grep -E 'client-data|worldserver'`. The server containers must have been created by a first `docker compose up`, and on fresh installs let the client-data download finish before copying, or it will overwrite your files.)
    * **Local:** Copy files into the `dbc` folder under the `DataDir` set in `worldserver.conf` (default `/path/to/server/env/dist/data/dbc/`).
5. **Apply C++ core patch (Required for Combo Points):** Apply the C++ core patch to `Unit.cpp` to broadcast custom `SpellDraftCP` addon messages.

   Here is the Python script:
   ```python
   # patch_unit.py
   import sys
   u = "../../src/server/game/Entities/Unit/Unit.cpp"
   c = open(u, "r", encoding="utf-8").read()
   t = "playerMe->SendDirectMessage(&data);"
   r = t + """

        // Send custom SpellDraft addon message for custom combo point rendering
        std::string prefix = "SpellDraftCP";
        std::string message = std::to_string(m_comboPoints);
        std::string fullmsg = prefix + "\\t" + message;

        WorldPacket addonData(SMSG_MESSAGECHAT, 100);
        addonData << uint8(0); // CHAT_MSG_ADDON (Whisper/Normal channel context)
        addonData << int32(LANG_ADDON);
        addonData << playerMe->GetGUID();
        addonData << uint32(0);
        addonData << playerMe->GetGUID();
        addonData << uint32(fullmsg.length() + 1);
        addonData << fullmsg;
        addonData << uint8(0);
        playerMe->GetSession()->SendPacket(&addonData);"""

   if t in c and "SpellDraftCP" not in c:
       open(u, "w", encoding="utf-8").write(c.replace(t, r, 1))
   ```

   You can execute this patch directly from the `modules/mod-spelldraft/` directory in a single line:
   ```bash
   python3 -c 'import sys; u="../../src/server/game/Entities/Unit/Unit.cpp"; c=open(u,"r",encoding="utf-8").read(); t="playerMe->SendDirectMessage(&data);"; r=t+"\n\n        // Send custom SpellDraft addon message for custom combo point rendering\n        std::string prefix = \"SpellDraftCP\";\n        std::string message = std::to_string(m_comboPoints);\n        std::string fullmsg = prefix + \"\\t\" + message;\n\n        WorldPacket addonData(SMSG_MESSAGECHAT, 100);\n        addonData << uint8(0); // CHAT_MSG_ADDON (Whisper/Normal channel context)\n        addonData << int32(LANG_ADDON);\n        addonData << playerMe->GetGUID();\n        addonData << uint32(0);\n        addonData << playerMe->GetGUID();\n        addonData << uint32(fullmsg.length() + 1);\n        addonData << fullmsg;\n        addonData << uint8(0);\n        playerMe->GetSession()->SendPacket(&addonData);"; open(u,"w",encoding="utf-8").write(c.replace(t,r,1) if t in c and "SpellDraftCP" not in c else c)'
   ```
6. **Rebuild server:** Compile the C++ module code:
   * **Docker:** Rebuild the container: `docker compose build ac-worldserver` (or `docker compose up -d --build`).
   * **Local:** Run your local CMake and compilation toolchain.
 7. **Install Client files:** Copy/merge the contents of the `wow-client/` directory directly into your World of Warcraft client folder (which merges the `Data/` (including `Data/enUS/` locale patches) and `Interface/` subdirectories).

</details>

---

## Updating the Module

If you are updating to the latest version of `mod-spelldraft`, follow these steps to apply updates safely without losing any database data or player character progress:

### 1. Pull the Latest Code
Navigate to your module directory and pull the latest updates from GitHub:
```bash
cd modules/mod-spelldraft
git pull
```

### 2. Run the Installer Script
Run the automated installation script to redeploy the updated Lua scripts, configuration files, and DBC/C++ compiler changes:
```bash
./install.sh
```
> [!NOTE]
> The installation script will check if your active `mod_spelldraft.conf` configuration exists. If it does, it will **skip overwriting it** to preserve your custom settings.

### 3. Reload or Restart
To apply the changes, reload the Eluna scripting engine in-game or restart your server:
* **Reload Eluna (No Downtime):** Type `.eluna reload` in-game as a GM to immediately hot-reload the updated scripts. Affected players will just need to log out and back in to apply the updates.
* **Server Reboot:** Restart your worldserver container or process (e.g. `podman restart ac-worldserver` or `docker compose restart ac-worldserver`).

### 4. Update the Client Addon
Since updates may contain client-side fixes, copy the updated Addon files to your local game client:
* **Copy AddOn:** Copy the contents of `wow-client/Interface/AddOns/SpellDraft/` to your WoW client's `Interface/AddOns/SpellDraft/` directory, overwriting the old files.
* **Reload UI:** In-game, type `/reload` in the chat window to load the new AddOn layout.

---

## Configuration File Parameters

You can customize the draft system parameters by editing `lua_scripts/spelldraft_config.lua`:

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `GAME_MODE` | `"traditional"` | What a **brand-new** character starts as. `"traditional"`: keeps the class it was created with and may pick one optional second class (mod-multiclass), with the Grimoire offering both classes' talent trees. `"draft"`: the original classless SpellDraft start. Existing characters keep their stored `draft_state` either way. Any value that is not exactly `"draft"` is treated as `"traditional"`, so a typo cannot silently disable drafting. |
| `MAX_LEVEL` | `80` | Level required to venture into Prestige Mode via gossip. |
| `NPC_ID` | `2069426` | Custom Chromie NPC gossip trigger. |
| `DRAFT_MODE_REROLLS` | `2` | Base reroll tokens given to characters starting a draft run (prestige 0). |
| `DRAFT_MODE_SPELLS` | `1` | Base number of spells a player gets when starting a draft. |
| `PRESTIGE1_REROLLS` | `5` | Starting rerolls granted at prestige 1. |
| `PRESTIGE1_REROLLS_PER_LEVEL` | `1` | Rerolls earned per level-up at prestige 1. |
| `PRESTIGE_REROLL_SCALING` | `2` | Reroll scaling increment added to both starting pool and per-level rerolls for each prestige rank beyond rank 1. |
| `DRAFT_BANS_START` | `5` | Initial bans given to characters to prune the spell pool. |
| `INCLUDE_RARITY_5` | `false` | Enable/disable broken/racial passives and infinitely spammable spells in the draft pool. |
| `REROLLS_PER_LEVELUP` | `0` | Rerolls earned per level-up at prestige 0 (none until first prestige). |
| `UNLIMITED_REROLLS_FIRST_DRAW` | `false` | When enabled, rerolls are free and unlimited until the character picks the very first spell of a draft run (`successful_drafts == 0`), regardless of class or level. The Reroll button shows `Reroll (∞)` while active; normal reroll accounting resumes after the first pick. Applies again on each prestige run, since the pick counter resets. |
| `CROSS_FACTION_PORTALS` | `false` | When enabled, all Portal/Teleport spells (both factions' capitals plus Theramore, Stonard, Shattrath, Dalaran, and Karazhan) are injected into the draft pool for both factions — Alliance characters can draft Horde city teleports and vice versa. Uses each spell's own rarity (teleports Common, portals Epic) and respects level requirements, bans, and already-known spells. |
| `POOL_AMOUNT` | `45` | The number of spells pooled from the full DB on every new draft. Every time a player reaches a level-up or consumes a Lost Grimoire, the system runs a database query to select 45 random, level-appropriate class abilities based on your configured rarity distribution. Rerolls select from this cached pool in memory instead of repeating heavy database queries, keeping server load minimal. |
| `RARITY_DISTRIBUTION` | `[0]=0.50, [1]=0.27, ...` | Probability ratios for Common (`[0]`), Uncommon (`[1]`), Rare (`[2]`), Epic (`[3]`), Legendary (`[4]`). |

### Worldserver Configuration (`mod_spelldraft.conf`)

The C++ side of the module reads `etc/modules/mod_spelldraft.conf` (created from `conf/mod_spelldraft.conf.dist` by the installer):

| Setting | Default | Description |
| :--- | :--- | :--- |
| `SpellDraft.Enable` | `1` | Enables the C++ hooks (custom weapon/armor proficiencies, secondary power bars, druid form casting). Does not affect the Eluna Lua scripts. |
| `SpellDraft.AllowSpellsInDruidForms` | `0` | Controls casting while in Druid shapeshift forms (Cat, Bear, Dire Bear, Travel, Aquatic, Tree of Life, Moonkin). See modes below. |

`SpellDraft.AllowSpellsInDruidForms` modes:

* **`0` — Disabled**: native WoW rules; casting a non-form spell fails or unshifts as usual.
* **`1` — All**: any spell can be cast in any Druid form. The server skips the `SPELL_FAILED_ONLY_SHAPESHIFT` / `SPELL_FAILED_NOT_SHAPESHIFT` checks entirely for players.
* **`2` — ME (Mystic Enchants)**: form casting is only unlocked by Mystic Enchants, each covering one class family on one form group. A full set ships in `data/sql/db-world/26_druid_form_casting_enchant.sql`:
  * **Epic tier** (40 enchants): one class on one form — `<Class-flavor> Bear / Prowler / Moonkin / Treant` (e.g. *Feltouched Bear* = Warlock in Bear/Dire Bear, *Arcanebound Prowler* = Mage in Cat).
  * **Legendary tier** (4 enchants, rarest): **all** classes on one form — *Heart of Ursoc* (Bear), *Grace of Ashamane* (Cat), *Gift of Elune* (Moonkin), *Blessing of Nordrassil* (Tree of Life).
  * Rules are data-driven: the C++ reads `custom_form_casting_rules` (`marker_aura`, `spell_family` — 0 = any class, `form_mask` — bit = form id − 1) at startup, so new enchants need only SQL (marker aura in `spell_dbc` + `custom_random_enchantments` row + rule row) and a server restart.

> **Client patch required for modes 1 and 2:** this setting only lifts *server-side* validation. Without the SpellDraft client patch (`patch-P.mpq`, or the compiled `-z` patch on HD clients), the client itself still auto-unshifts or greys out spell buttons while in forms. The patch sets the stance flag on the Druid forms in `SpellShapeshiftForm.dbc` and clears Druid form exclusions from `StancesNot` in `Spell.dbc`.

### Prestige Shop Customization

The Prestige Shop inventory, item details, and token costs are defined and can be modified in two files:
1.  **Server-Side Costs:** The server-side cost validation is mapped in [spell_choice.lua](file:///home/bdodroid/wow-server-playerbots/modules/mod-spelldraft/lua/SpellDraft/spell_choice.lua#L927-L973) under the `costs` table in the `HandleBuyShopItem` function.
2.  **Client-Side UI:** The shop item entries, categories, descriptions, and displayed token costs are configured in [PrestigeShop.lua](file:///home/bdodroid/wow-server-playerbots/modules/mod-spelldraft/addon/SpellDraft/PrestigeShop.lua#L3-L75) under the `shopItems` table.

---

### Database-Level Loot Tuning

Because loot tables are applied once to the database during server startup/migration, drop rates are configured directly within the SQL files rather than the Lua config. 

To tune these drop rates, edit the `Chance` columns at the bottom of [05_prestige_draft_items.sql](data/sql/db-world/base/05_prestige_draft_items.sql) and the matching update statements in [08_consumable_id_swap.sql](data/sql/db-world/base/08_consumable_id_swap.sql).

| Item | Default (Normal/Elite) | Default (Bosses) | Location in SQL |
| :--- | :--- | :--- | :--- |
| **Scroll of Reroll** (`4427`) | `0.6%` | `10.0%` | `05_prestige_draft_items.sql` / `08_consumable_id_swap.sql` |
| **Scroll of Ban** (`1078`) | `0.6%` | `10.0%` | `05_prestige_draft_items.sql` / `08_consumable_id_swap.sql` |
| **Lost Grimoire** (`13149`) | `0.1%` | `5.0%` | `05_prestige_draft_items.sql` |
| **Tome of Talents** (`25462`) | `1.0%` | `15.0%` | `05_prestige_draft_items.sql` |


## GM Commands for Testing Consumable Items

For testing and verification in-game, you can use the following `.additem` commands to spawn the customized draft consumables:

*   **Tome of Talents**: `.additem 25462 <count>` (triggers passive talent drafting & progressive rank upgrading)
*   **Lost Grimoire**: `.additem 13149 <count>` (triggers an immediate bonus active spell draft)
*   **Scroll of Reroll**: `.additem 4427 <count>` (adds +1 Reroll charges)
*   **Scroll of Ban**: `.additem 1078 <count>` (adds +1 Ban charges)

### Mystic Enchants
*   `.rollre` — force-rolls a Mystic Enchant on every eligible weapon/armor item you carry (equipped + bags) at 100% chance; re-running it rerolls them.
*   Enchant services UI: talk to **Nibbs the Imp** (NPC `99000`) → *Open Mystic Enchant services*.

### Custom Glyphs
*   **Glyph of the Orca** (minor, cosmetic): `.additem 100001`
*   **Glyph of the Zealot** (major, effect): `.additem 100002`
*   Beta cosmetic glyphs: `.additem 40484` (White Bear), `.additem 40948` (Red Lynx), `.additem 43336` (Black Bear), `.additem 43337` (Forest Lynx), `.additem 43384` (Black Wolf)
*   Open the talent window → **Glyphs** tab, click the glyph item, then click a matching socket (level 15+). Minor glyphs morph the listed form; check effect glyphs with their combat proc.
*   Forgotten Grimoire spawns: `.go xyz -10782 -1378 40 0` (Duskwood), `.go xyz -7580 199 12 1` (Silithus), `.go xyz 4110 -4740 101 571` (Grizzly Hills).

---

## Testing & Verification

Three layers, cheapest first. None of them need a rebuild.

1. **Static checks** — `python3 apps/codestyle/codestyle-cpp.py <files>` and `codestyle-sql.py <files>`; plus `python3 tools/generate_talent_data.py --check` and `python3 tools/report_talent_changes.py --check` for drift between the generated data and the committed files.
2. **The Eluna self-test rig** — assertions about talents, skills, spellbook and power that only the worldserver can see, scored from the log. It is off by default because most batteries mutate the character they run on.
   ```bash
   # enable in the deployed lua_scripts/spelldraft_config.lua, then log in a
   # character named "Sdtest*" (or whisper yourself SD_SELFTEST), then:
   python3 tools/run_selftest.py
   ```
   `tools/run_selftest.py --battery <name>` scores one battery, `--all-runs` every run in the log window, `--file` a saved log; exit code 2 means the rig never ran. The batteries are `smoke` (read-only), `multiclass_identity`, `hybrid_power` and `talent_skill_state` — the last one asserts the per-class proficiency contract and the drop-it-again revocation. Deeper notes live in `docs/SELFTEST.md` (local, like the other `docs/` files — see below).
3. **DB/state probes** — for anything about what the server actually loaded, ask it rather than reading the SQL: `spell_dbc` is the effective row for an overridden spell, and `talent_dbc` for the talent trees.

Note that `docs/` is gitignored on purpose: it holds working documents (talent reports, the redesign plan, the spell registry) that are written and regenerated locally, not shipped with the module.

### Documents that are generated — regenerate, don't hand-edit

| document | generator |
|---|---|
| `docs/TALENT_SYNERGY.md` | `python3 tools/classify_talent_synergy.py --apply-spell-dbc --out docs/TALENT_SYNERGY.md` |
| `docs/TALENT_CHANGES.md` | `python3 tools/report_talent_changes.py` |
| `docs/TALENT_TOOLTIPS.md` | `python3 tools/reword_talent_tooltips.py` |
| `SpellData_Talents.lua`, `talent_dbc` dumps | `python3 tools/generate_talent_data.py` |

**Pass `--apply-spell-dbc`** (or the equivalent flag) to the classifier: without it the
report describes the raw `Spell.dbc` and ignores every scoping change made in SQL, which
silently produces very different numbers (350 vs 156 `needs-redesign` chains as of
2026-09-20). The report now records which mode produced it, at the top.

### Adding a custom spell

Read `docs/CUSTOM_SPELLS.md` (local) first — it is the id registry plus the rule that
decides whether a spell needs a client `Spell.dbc` row (anything a player presses) or
only a `spell_dbc` row (anything only the server casts). In short: **a serverside-only
spell is invisible to the client**, so a player-facing ability has to be authored into
the client patch the way `tools/eq_spell_pack.json` does it.

---

## Building Client Patches for HD Repacks

The repository ships `wow-client/Data/patch-P.mpq` built for the **native 3.3.5a client only**. A client counts as "native" only if its `Data/` folder contains nothing beyond Blizzard's archives (`common`, `expansion`, `lichking`, `patch`, `patch-2`, `patch-3` + locale equivalents) — any extra lettered `patch-*.mpq` (HD model packs, repack content) means you need a custom compile, even if the install is labelled a clean client. HD / custom repack clients need their own compile, for two reasons:

1. **Repacks ship modified DBCs.** They replace creature meshes/textures and often far more (one tested repack carries a 67 MB custom `Spell.dbc` in `patch-enUS-s.mpq`). Overriding those tables with native-based files breaks the repack: neon-green/invisible creature models, altered tooltips, and dangling database references that can destabilize the client. The patch must be compiled from the DBCs *your* repack actually uses — every repack is different, so no prebuilt HD archive is shipped.
2. **Repacks ship high-letter patches.** MPQ archives load in slot order (`patch-2..9`, then `patch-a..z`, locale patches outranking base ones at the same letter). A repack's own `patch-enUS-s.mpq` outranks `patch-P.mpq`, silently disabling SpellDraft's data — so HD builds are emitted as a **locale `-z` patch**, which outranks everything.

The two bundled tools handle this (no external MPQ software needed):

1. **Extract the client's effective DBCs** — the extractor walks the repack's full archive chain in load order and pulls out the version of each table the client actually resolves:
   ```bash
   python3 tools/extract_client_dbcs.py "/path/to/your hd client" /path/to/dbc_src
   ```
2. **Compile with an HD locale override patch:**
   ```bash
   python3 tools/build_client_patch.py --dbc-src /path/to/dbc_src --hd-locale enUS
   ```
   (Match `--hd-locale` to the client's locale folder, e.g. `enGB`, `deDE`.)
3. **Deploy** the resulting `wow-client/Data/enUS/patch-enUS-z.mpq` into the client's `Data/enUS/` folder. Do **not** also deploy `patch-P.mpq` — exactly one SpellDraft archive per client, ever (see the ERROR #132 warning in the connection guide).

Since all custom spells, items, glyphs, and models are defined in the single source of truth (`tools/client_patch_manifest.json`), compiling with your client's own database files as a base fully preserves all repack customizations while seamlessly adding all module features.

---

## Credits & Inspiration

This project is heavily inspired by and uses elements from the original [Prestige and Draft Mode](https://github.com/Youpeoples/Prestige-and-Draft-Mode) project by **Youpeoples** (Stephen Kania). 

We would like to extend our sincere thanks to **Youpeoples** and all contributors to the original repository for their awesome work and foundational layouts that made this custom classless drafting and prestige system possible!

---

## License

This project is completely open source. Anyone is free to copy, modify, distribute, or use any code, assets, or resources in this project for their own custom WoW server or any other purpose without restriction.
