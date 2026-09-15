-- EverQuest-inspired classic/legacy items.
--
-- Entry block 100006-100013 (the module's custom item range continues from
-- 100005). Every item is deliberately unrestricted: AllowableClass = -1, so
-- anything can be equipped by anything, matching mod-spelldraft's universal
-- weapon/armor proficiency design. Visuals reuse existing `displayid`s, so no
-- client-side item art is needed.
--
-- Proc/use effects point at spells from the EQ spell pack (993xxx, shipped in
-- the patched Spell.dbc via tools/build_client_patch.py). spelltrigger:
-- 0 = ON_USE, 1 = ON_EQUIP, 2 = CHANCE_ON_HIT (see ItemTemplate.h).
-- Deliberately overtuned by design.

DELETE FROM `item_template` WHERE `entry` BETWEEN 100006 AND 100013;

INSERT INTO `item_template`
    (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`,
     `BuyPrice`, `SellPrice`, `InventoryType`, `AllowableClass`, `AllowableRace`,
     `ItemLevel`, `RequiredLevel`, `maxcount`, `stackable`, `bonding`, `Material`, `sheath`,
     `stat_type1`, `stat_value1`, `stat_type2`, `stat_value2`, `stat_type3`, `stat_value3`,
     `dmg_min1`, `dmg_max1`, `dmg_type1`, `delay`, `armor`,
     `spellid_1`, `spelltrigger_1`, `spellcharges_1`, `spellppmRate_1`, `spellcooldown_1`,
     `description`)
VALUES
-- Manastone: the infamous clicky. Burns your own life for a huge mana refill,
-- no cooldown, exactly as it is remembered.
    (100006, 4, 0, 'Manastone', 8232, 4, 0,
     0, 25000, 12, -1, -1,
     80, 1, 1, 1, 0, 1, 0,
     5, 40, 0, 0, 0, 0,
     0, 0, 0, 0, 0,
     993034, 0, -1, 0, -1,
     'Converts your life force directly into mana. The Combine did not consider the consequences.'),

-- Fungi Tunic: famous for its passive regeneration.
    (100007, 4, 2, 'Fungi Tunic', 31797, 4, 0,
     0, 30000, 5, -1, -1,
     80, 1, 0, 1, 0, 8, 0,
     7, 60, 6, 40, 5, 30,
     0, 0, 0, 0, 700,
     993035, 1, 0, 0, -1,
     'Woven from the fungi of the underdark. Its spores knit flesh without pause.'),

-- Soul Leech: drains life on hit.
    (100008, 2, 15, 'Soul Leech', 64671, 4, 0,
     0, 50000, 13, -1, -1,
     80, 1, 0, 1, 0, 1, 3,
     3, 60, 7, 45, 0, 0,
     320, 480, 0, 1600, 0,
     993020, 2, -1, 0, -1,
     'The blade drinks first, and asks nothing.'),

-- Bladestorm: whirlwind of steel on hit.
    (100009, 2, 8, 'Bladestorm', 35097, 5, 0,
     0, 90000, 17, -1, -1,
     80, 1, 0, 1, 0, 1, 3,
     4, 90, 7, 70, 0, 0,
     980, 1470, 0, 3400, 0,
     993031, 2, -1, 0, -1,
     'Every swing becomes a storm.'),

-- Poison Wind Censer: AoE poison cloud on hit (EQ Monk epic).
    (100010, 2, 13, 'Poison Wind Censer', 64462, 4, 0,
     0, 60000, 13, -1, -1,
     80, 1, 0, 1, 0, 1, 1,
     3, 70, 7, 50, 0, 0,
     390, 560, 0, 2000, 0,
     993032, 2, -1, 0, -1,
     'A censer of choking wind, swung in the hands of the disciplined.'),

-- Rubicite Armor: iconic red plate, with regeneration.
    (100011, 4, 4, 'Rubicite Breastplate', 33635, 4, 0,
     0, 45000, 5, -1, -1,
     80, 1, 0, 1, 0, 6, 0,
     4, 80, 7, 90, 12, 40,
     0, 0, 0, 0, 1800,
     993036, 1, 0, 0, -1,
     'Blood-red plate of a lost forging. The metal remembers how to mend itself.'),

-- Earthshaker: AoE stun proc (EQ Warrior epic).
    (100012, 2, 5, 'Earthshaker', 29698, 5, 0,
     0, 90000, 17, -1, -1,
     80, 1, 0, 1, 0, 1, 3,
     4, 95, 7, 75, 0, 0,
     1010, 1515, 0, 3500, 0,
     993003, 2, -1, 0, -1,
     'Strike the earth and the earth answers.'),

-- Fiery Avenger: burns the target, mends the wielder (EQ Paladin epic).
    (100013, 2, 7, 'Fiery Avenger', 30606, 5, 0,
     0, 80000, 13, -1, -1,
     80, 1, 0, 1, 0, 1, 3,
     4, 65, 7, 55, 5, 35,
     420, 620, 0, 2600, 0,
     993033, 2, -1, 0, -1,
     'Righteous flame, kindled for those who stand between.');
