-- Melee talent rework - the DB side of the new Enhancement/Retribution talents
-- (see .agents/plans/melee-talent-rework/). The spells themselves live in the
-- patched Spell.dbc (tools/eq_spell_pack.json, ids 993301+ / 993310+) and the
-- talent rows in 06_talent_dbc.sql; this file only carries what the engine reads
-- out of the database.
--
-- 1. spell_script_names - a SpellScript/AuraScript is inert without its binding
--    row (see .agents/docs/cpp-scripts.md). Both proc talents and all three
--    Crusader Strike ranks are bound here.
DELETE FROM `spell_script_names` WHERE `ScriptName` IN
    ('spell_sha_gale_force', 'spell_pal_crusaders_fury', 'spell_pal_crusader_strike_killing_blow');
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES
    (993307, 'spell_sha_gale_force'),
    (993316, 'spell_pal_crusaders_fury'),
    (35395, 'spell_pal_crusader_strike_killing_blow'),
    (993313, 'spell_pal_crusader_strike_killing_blow'),
    (993314, 'spell_pal_crusader_strike_killing_blow');

-- 2. spell_proc - what makes the two proc talents proc at all. Only spells with a
--    row here participate in the proc system (Aura::GetProcEffectMask returns 0
--    without one), and the family/flag columns are what narrow the proc to a
--    single ability: family 11 + SpellFamilyMask1 16 is Stormstrike (and the
--    32175/32176 weapon-damage triggers it fires), family 10 + 32768 is Crusader
--    Strike. ProcFlags 16 (PROC_FLAG_DONE_SPELL_MELEE_DMG_CLASS) requires
--    SpellPhaseMask 2 (PROC_SPELL_PHASE_HIT, enforced at load); HitMask 2
--    (PROC_HIT_CRITICAL) is the crit-only filter; SpellTypeMask 1 is
--    PROC_SPELL_TYPE_DAMAGE (what the engine defaults this flag pair to).
--    Chance 10 = Gale Force's 10%; 100 = Crusader's Fury's "every crit".
DELETE FROM `spell_proc` WHERE `SpellId` IN (993307, 993316);
INSERT INTO `spell_proc` (`SpellId`, `SchoolMask`, `SpellFamilyName`, `SpellFamilyMask0`, `SpellFamilyMask1`, `SpellFamilyMask2`, `ProcFlags`, `SpellTypeMask`, `SpellPhaseMask`, `HitMask`, `AttributesMask`, `DisableEffectsMask`, `ProcsPerMinute`, `Chance`, `Cooldown`, `Charges`) VALUES
    (993307, 0, 11, 0, 16,    0, 16, 1, 2, 2, 0, 0, 0, 10,  0, 0),
    (993316, 0, 10, 0, 32768, 0, 16, 1, 2, 2, 0, 0, 0, 100, 0, 0);

-- 3. spell_ranks - Crusader Strike's rank chain, 35395 -> 993313 (5 yd) ->
--    993314 (10 yd), learned by Crusading Zealot's ranks. Player::addSpell uses
--    the chain to swap the action-bar button when a higher rank is learned
--    (SMSG_SUPERCEDED_SPELL), and the three ranks keep R1's category/recovery so
--    they share one cooldown.
DELETE FROM `spell_ranks` WHERE `first_spell_id` = 35395 OR `spell_id` IN (35395, 993313, 993314);
INSERT INTO `spell_ranks` (`first_spell_id`, `spell_id`, `rank`) VALUES
    (35395, 35395, 1),
    (35395, 993313, 2),
    (35395, 993314, 3);
