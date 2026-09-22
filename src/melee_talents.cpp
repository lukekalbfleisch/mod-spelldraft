/*
 * Melee talent rework scripts - see .agents/plans/melee-talent-rework/.
 *
 * Two talents need behaviour a DBC row cannot express, so each pairs its learned
 * spell with a `spell_proc` row (SQL, 35_melee_talent_rework.sql) and one of the
 * scripts below:
 *
 *   Gale Force (993307)      - 10% chance on a Stormstrike critical strike to
 *                              finish Stormstrike's cooldown. "Reset a cooldown"
 *                              is not a spell effect, hence a script.
 *   Crusader's Fury (993316) - a 10s window in which Crusader Strike has no
 *                              cooldown (a -100% SPELLMOD_COOLDOWN aura from the
 *                              spell itself), extended +1s per Crusader Strike
 *                              critical strike (the proc) or killing blow (the
 *                              SpellScript at the bottom), hard-capped at 20s.
 *
 * The proc rows are what make the targeting work at all: family 11 + flag[1] bit
 * 4 is Stormstrike (and the 32175/32176 weapon-damage triggers it fires), family
 * 10 + flag[1] bit 15 is Crusader Strike - the same family/flag mechanism stock
 * "Improved X" talents rely on. Without the row the auras never proc.
 */

#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuras.h"
#include "SpellScript.h"

#include <algorithm>

enum MeleeTalentSpells
{
    SPELL_SHAMAN_STORMSTRIKE       = 17364,
    SPELL_SHAMAN_GALE_FORCE        = 993307,
    SPELL_PALADIN_CRUSADERS_FURY   = 993316,
};

// Crusader's Fury: 1 sec per critical strike / killing blow, capped at 20 sec.
int32 const CRUSADERS_FURY_EXTENSION_MS = 1000;
int32 const CRUSADERS_FURY_MAX_MS       = 20000;

// Extend an active Crusader's Fury window. Shared by the crit proc and the
// killing-blow hook so both paths apply the same cap.
static void ExtendCrusadersFury(Unit* owner)
{
    if (!owner)
        return;

    Aura* fury = owner->GetAura(SPELL_PALADIN_CRUSADERS_FURY);
    if (!fury)
        return;

    fury->SetDuration(std::min<int32>(fury->GetDuration() + CRUSADERS_FURY_EXTENSION_MS, CRUSADERS_FURY_MAX_MS));
}

// 993307 - Gale Force (Enhancement talent 3002, 1 rank).
class spell_sha_gale_force : public AuraScript
{
    PrepareAuraScript(spell_sha_gale_force)

    void HandleProc(ProcEventInfo& /*eventInfo*/)
    {
        Player* player = GetUnitOwner()->ToPlayer();
        if (!player)
            return;

        if (player->HasSpellCooldown(SPELL_SHAMAN_STORMSTRIKE))
            player->RemoveSpellCooldown(SPELL_SHAMAN_STORMSTRIKE, true);
    }

    void Register() override
    {
        AfterProc += AuraProcFn(spell_sha_gale_force::HandleProc);
    }
};

// 993316 - the Crusader's Fury no-cooldown window (Retribution talent 3004).
class spell_pal_crusaders_fury : public AuraScript
{
    PrepareAuraScript(spell_pal_crusaders_fury)

    void HandleProc(ProcEventInfo& /*eventInfo*/)
    {
        ExtendCrusadersFury(GetUnitOwner());
    }

    void Register() override
    {
        AfterProc += AuraProcFn(spell_pal_crusaders_fury::HandleProc);
    }
};

// 35395 / 993313 / 993314 - Crusader Strike, every rank.
//
// A killing blow is not a proc the engine can narrow to one ability: PROC_FLAG_KILL
// is raised with no spell info at all (Unit::Kill), so a family/flag filter cannot
// tell a Crusader Strike kill from any other. The hit hook can: it runs after this
// spell's own damage has been applied, so a dead hit unit means Crusader Strike
// landed the killing blow.
class spell_pal_crusader_strike_killing_blow : public SpellScript
{
    PrepareSpellScript(spell_pal_crusader_strike_killing_blow)

    void HandleAfterHit()
    {
        if (GetHitUnit() && GetHitUnit()->isDead())
            ExtendCrusadersFury(GetCaster());
    }

    void Register() override
    {
        AfterHit += SpellHitFn(spell_pal_crusader_strike_killing_blow::HandleAfterHit);
    }
};

void AddMeleeTalentScripts()
{
    RegisterSpellScript(spell_sha_gale_force);
    RegisterSpellScript(spell_pal_crusaders_fury);
    RegisterSpellScript(spell_pal_crusader_strike_killing_blow);
}
