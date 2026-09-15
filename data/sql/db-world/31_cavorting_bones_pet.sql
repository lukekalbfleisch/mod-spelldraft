-- Cavorting Bones rework: a permanent pet (like a Warlock/Hunter pet), not a
-- timed Guardian summon. New creature entry 990100 ("Cavorting Bones"),
-- cloned from the native Summoned Skeleton (11200) via a temp table (so every
-- NOT NULL column with no sensible default is already populated correctly
-- regardless of this AzerothCore version's exact creature_template column
-- list/order - both surprised us more than once already, e.g. modelid1-4 and
-- spell1-4 having moved to separate linking tables), then adjusted for its
-- role as a permanent, player-controlled pet.
--
-- The C++ side (src/SpellDraft.cpp, OnPlayerBeforeGuardianInitStatsForLevel)
-- forces PetType::SUMMON_PET for this entry regardless of the owner's actual
-- class - Guardian::InitStatsForLevel (Pet.cpp) only does that automatically
-- for Warlock/Shaman/DK/Mage owners, which doesn't fit a classless server.
--
-- 28_eq_spell_pack.sql/993010 (Cavorting Bones, the summon spell) now uses
-- SPELL_EFFECT_SUMMON_PET targeting this entry instead of SPELL_EFFECT_SUMMON.

DROP TEMPORARY TABLE IF EXISTS `tmp_cavorting_bones_ct`;
CREATE TEMPORARY TABLE `tmp_cavorting_bones_ct` AS SELECT * FROM `creature_template` WHERE `entry` = 11200;
UPDATE `tmp_cavorting_bones_ct` SET
    `entry` = 990100,
    `name` = 'Cavorting Bones',
    `faction` = 73,     -- reused from the native Imp (416): a known-good "friendly to owner" pet faction
    `type` = 6,         -- CREATURE_TYPE_UNDEAD
    `HealthModifier` = 1.0,
    `ManaModifier` = 0; -- no mana - it's a melee pet, not a caster

DELETE FROM `creature_template` WHERE `entry` = 990100;
INSERT INTO `creature_template` SELECT * FROM `tmp_cavorting_bones_ct`;
DROP TEMPORARY TABLE `tmp_cavorting_bones_ct`;

DROP TEMPORARY TABLE IF EXISTS `tmp_cavorting_bones_model`;
CREATE TEMPORARY TABLE `tmp_cavorting_bones_model` AS SELECT * FROM `creature_template_model` WHERE `CreatureID` = 11200;
UPDATE `tmp_cavorting_bones_model` SET `CreatureID` = 990100;

DELETE FROM `creature_template_model` WHERE `CreatureID` = 990100;
INSERT INTO `creature_template_model` SELECT * FROM `tmp_cavorting_bones_model`;
DROP TEMPORARY TABLE `tmp_cavorting_bones_model`;

-- Base abilities the pet auto-learns (Pet::InitLevelupSpellsForLevel ->
-- GetPetDefaultSpellsEntry(GetEntry()), fed by this table - see
-- SpellMgr.cpp:LoadPetDefaultSpells). Bone Shard (993037) and Rattling Roar
-- (993038) are defined in 28_eq_spell_pack.sql.
DELETE FROM `creature_template_spell` WHERE `CreatureID` = 990100;
INSERT INTO `creature_template_spell` (`CreatureID`, `Index`, `Spell`) VALUES
    (990100, 0, 993037),
    (990100, 1, 993038);
