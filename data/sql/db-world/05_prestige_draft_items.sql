-- ----------------------------------------------------------------------------
-- These four items (Scroll of Reroll, Scroll of Ban, Lost Grimoire, Tome of
-- Talents) only matter in classless draft mode - the prestige-draft economy's
-- reroll/ban/bonus-draft/passive-draft currency. Traditional mode (two fixed
-- classes + native talent trees via /mct) is the server default and never
-- reads any of this, so world-drop loot for these items has no player who can
-- use it for most characters. World drops removed 2026-09-21 (and, for the
-- ids 08/36 migrated to, 2026-09-24); the item templates stay defined because
-- draft mode's own code paths (first-login Tome of Talents grant, the prestige
-- shop, the per-player drop roll in spelldraft_core.lua) still need them.
--
-- This file must not touch 17731, 30811, 13149 or 25462: all four are retail
-- quest items (Scroll of Celebras, Scroll of Demonic Unbanishing, Eldarathian
-- Tome of Summoning Vol. 1, Tome of Dusk) that 08_consumable_id_swap.sql and
-- 36_grimoire_id_swap.sql restore. Every re-apply of an earlier version of
-- this file (it is re-applied on its own, independent of file order — see
-- memory wow_spelldraft_module_sql_reapply) overwrote them again and deleted
-- their quest drops. The four draft items live at 4427, 1078, 2793 and 4156
-- instead; this file only ever names them by those final ids.
-- ----------------------------------------------------------------------------

-- 1. Clean up stale custom entries (99001, 99002, 99003)
DELETE FROM `item_template` WHERE `entry` IN (99001, 99002, 99003);

-- 2. Remove every world drop of the four draft consumables (idempotent: also
--    removes rows any earlier install of this module injected). They are
--    listed by their FINAL ids (Scroll of Reroll/Ban from 08, Lost
--    Grimoire/Tome of Talents from 36); no retail creature legitimately drops
--    any of the four, so this delete is always safe regardless of whether 08
--    or 36 has run yet. Draft-mode characters get their drops from
--    spelldraft_core.lua instead, which rolls only for players in draft mode
--    (CONFIG.DRAFT_CONSUMABLE_DROPS).
DELETE FROM `reference_loot_template` WHERE `Entry` = 99000;
DELETE FROM `creature_loot_template` WHERE `Reference` = 99000;
DELETE FROM `creature_loot_template` WHERE `Item` IN (4427, 1078, 2793, 4156);
