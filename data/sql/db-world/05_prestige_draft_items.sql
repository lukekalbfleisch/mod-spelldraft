-- ----------------------------------------------------------------------------
-- These four items (Scroll of Reroll, Scroll of Ban, Lost Grimoire, Tome of
-- Talents) only matter in classless draft mode - the prestige-draft economy's
-- reroll/ban/bonus-draft/passive-draft currency. Traditional mode (two fixed
-- classes + native talent trees via /mct) is the server default and never
-- reads any of this, so world-drop loot for these items has no player who can
-- use it for most characters. World drops removed 2026-09-21; the item
-- templates themselves stay defined (draft mode's own code paths, e.g.
-- spelldraft_core.lua's first-login Tome of Talents grant, still need them to
-- exist and behave correctly for whoever is in draft mode).
-- ----------------------------------------------------------------------------

-- 1. Clean up stale custom entries (99001, 99002, 99003)
DELETE FROM `item_template` WHERE `entry` IN (99001, 99002, 99003);

-- 2. Override existing unused retail templates to match our custom design
UPDATE `item_template` SET
  `class` = 0,
  `subclass` = 4,
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
  `Description` = 'Consuming this scroll grants you +1 Draft Reroll.'
WHERE `entry` = 17731;

UPDATE `item_template` SET
  `class` = 0,
  `subclass` = 4,
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
  `Description` = 'Consuming this scroll grants you +1 Draft Ban.'
WHERE `entry` = 30811;

UPDATE `item_template` SET
  `class` = 0,
  `subclass` = 0,
  `name` = 'Lost Grimoire',
  `Quality` = 3,
  `Flags` = 0,
  `BuyPrice` = 5000,
  `SellPrice` = 1250,
  `InventoryType` = 0,
  `RequiredLevel` = 1,
  `stackable` = 5,
  `maxcount` = 0,
  `spellid_1` = 24312,
  `spelltrigger_1` = 0,
  `spellcharges_1` = -1,
  `Material` = -1,
  `Description` = 'Consuming this grimoire triggers an immediate bonus spell draft.'
WHERE `entry` = 13149;

UPDATE `item_template` SET
  `class` = 12,
  `subclass` = 0,
  `name` = 'Tome of Talents',
  `Quality` = 3,
  `Flags` = 0,
  `BuyPrice` = 5000,
  `SellPrice` = 1250,
  `InventoryType` = 0,
  `RequiredLevel` = 1,
  `stackable` = 5,
  `maxcount` = 0,
  `spellid_1` = 24312,
  `spelltrigger_1` = 0,
  `spellcharges_1` = -1,
  `Material` = -1,
  `Description` = 'Consuming this grimoire triggers a passive class talent draft.'
WHERE `entry` = 25462;

-- 3. Clean up reference loot templates and direct loot entries (idempotent:
--    also removes any rows a prior install of this file injected).
DELETE FROM `reference_loot_template` WHERE `Entry` = 99000;
DELETE FROM `creature_loot_template` WHERE `Reference` = 99000;
DELETE FROM `creature_loot_template` WHERE `Item` IN (17731, 30811, 13149, 25462);
