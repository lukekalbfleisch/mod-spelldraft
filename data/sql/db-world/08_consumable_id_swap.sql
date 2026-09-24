-- ----------------------------------------------------------------------------
-- Scroll of Reroll and Scroll of Ban live at 4427 and 1078 (both deprecated,
-- dropless retail templates). They used to hijack 17731 and 30811, which are
-- retail quest items; this file moves the scrolls off them and restores both.
--
-- No world drop is defined here or anywhere in SQL: draft consumables drop only
-- for characters in draft mode, rolled per player in spelldraft_core.lua
-- (CONFIG.DRAFT_CONSUMABLE_DROPS). 05_prestige_draft_items.sql deletes any
-- leftover loot rows for them.
-- ----------------------------------------------------------------------------

-- 1. Swap target templates to entries 4427 (Scroll of Reroll) and 1078 (Scroll of Ban)
UPDATE `item_template` SET
  `class` = 0,
  `subclass` = 8,
  `name` = 'Scroll of Reroll',
  `Quality` = 2,
  `Flags` = 0,
  `BuyPrice` = 1000,
  `SellPrice` = 250,
  `InventoryType` = 0,
  `RequiredLevel` = 1,
  `stackable` = 20,
  `maxcount` = 0,
  `spellid_1` = 24312,
  `spelltrigger_1` = 0,
  `spellcharges_1` = -1,
  `Material` = 4,
  `bonding` = 0,
  `PageText` = 0,
  `Description` = 'Consuming this scroll grants you +1 Draft Reroll.'
WHERE `entry` = 4427;

UPDATE `item_template` SET
  `class` = 12,
  `subclass` = 0,
  `name` = 'Scroll of Ban',
  `Quality` = 2,
  `Flags` = 0,
  `BuyPrice` = 1000,
  `SellPrice` = 250,
  `InventoryType` = 0,
  `RequiredLevel` = 1,
  `stackable` = 20,
  `maxcount` = 0,
  `spellid_1` = 24312,
  `spelltrigger_1` = 0,
  `spellcharges_1` = -1,
  `Material` = 4,
  `bonding` = 0,
  -- 1078 was a readable letter; a nonzero PageText makes the client open the
  -- reading UI on right-click instead of using the item.
  `PageText` = 0,
  `Description` = 'Consuming this scroll grants you +1 Draft Ban.'
WHERE `entry` = 1078;

-- 2. Restore the hijacked retail item templates (17731 and 30811) to their
--    base-data values (data/sql/base/db_world/item_template.sql)
UPDATE `item_template` SET
  `class` = 12,
  `subclass` = 0,
  `name` = 'Scroll of Celebras',
  `Quality` = 1,
  `Flags` = 64,
  `BuyPrice` = 0,
  `SellPrice` = 0,
  `InventoryType` = 0,
  `RequiredLevel` = 0,
  `stackable` = 1,
  `maxcount` = 1,
  `spellid_1` = 0,
  `spelltrigger_1` = 0,
  `spellcharges_1` = 0,
  `Material` = -1,
  `bonding` = 4,
  `Description` = ''
WHERE `entry` = 17731;

UPDATE `item_template` SET
  `class` = 0,
  `subclass` = 0,
  `name` = 'Scroll of Demonic Unbanishing',
  `Quality` = 1,
  `Flags` = 64,
  `BuyPrice` = 700,
  `SellPrice` = 175,
  `InventoryType` = 0,
  `RequiredLevel` = 0,
  `stackable` = 20,
  `maxcount` = 0,
  `spellid_1` = 37834,
  `spelltrigger_1` = 0,
  `spellcharges_1` = -1,
  `Material` = -1,
  `bonding` = 4,
  `Description` = ''
WHERE `entry` = 30811;

-- 3. Restore the retail drop of Scroll of Demonic Unbanishing (base data:
--    Sunfury Warlock/Summoner, 35%, quest-required), which earlier installs of
--    05 deleted. Scroll of Celebras has no creature drop in retail data, so any
--    row an earlier version of this file invented for it is removed.
DELETE FROM `creature_loot_template` WHERE `Entry` = 12225 AND `Item` = 17731;

DELETE FROM `creature_loot_template` WHERE `Entry` IN (21503, 21505) AND `Item` = 30811;
INSERT INTO `creature_loot_template` (`Entry`, `Item`, `Reference`, `Chance`, `QuestRequired`, `LootMode`, `GroupId`, `MinCount`, `MaxCount`, `Comment`) VALUES
(21503, 30811, 0, 35, 1, 1, 0, 1, 1, 'Sunfury Warlock - Scroll of Demonic Unbanishing'),
(21505, 30811, 0, 35, 1, 1, 0, 1, 1, 'Sunfury Summoner - Scroll of Demonic Unbanishing');
