--[[
    Read-only smoke battery.

    Proves the whole pipeline end to end - trigger fires, assertions run, lines
    reach the worldserver log, tools/run_selftest.py scores them - without
    changing anything about the character it runs on. That makes it the safe
    battery to run against a real character you care about; every other battery
    mutates state and only restores it on the way out.

    It asserts only things that must be true of any logged-in character, so a
    failure here means the rig is wrong, not the server.
]]

SelfTest = SelfTest or {}
SelfTest.batteries = SelfTest.batteries or {}
SelfTest.order = SelfTest.order or {}

SelfTest.register("smoke", function(t, player)
    t.section("identity")

    local class = player:GetClass()
    t.check("class id is a playable class", class >= 1 and class <= 11, class, "1..11")

    local level = player:GetLevel()
    t.check("level is in range", level >= 1 and level <= 80, level, "1..80")

    t.assert_true("character is in world", player:IsInWorld())
    t.assert_true("character has a name", (player:GetName() or "") ~= "")

    t.section("multiclass state (read-only)")

    -- CONFIG.GetSecondaryClassId already handles the module-absent case by
    -- returning 0, so this doubles as a check that the column is reachable.
    local secondary = CONFIG.GetSecondaryClassId(player)
    t.check("secondary class id is valid or absent",
            secondary == 0 or (secondary >= 1 and secondary <= 11),
            secondary, "0 or 1..11")
    t.assert_false("secondary class differs from primary", secondary == class)

    local classSet = CONFIG.GetPlayerClassSet(player)
    t.assert_true("class set contains the primary class", classSet[class] == true)

    t.section("resources and skills")

    -- Power type 0 is mana. Every character has a max, even when it is zero.
    local maxMana = player:GetMaxPower(0)
    t.check("max mana is a number", type(maxMana) == "number", type(maxMana), "number")
    t.note("max mana", maxMana)
    t.note("free talent points", player:GetFreeTalentPoints())

    -- The racial language skill is the regression guard for the Blood Elf
    -- missing-language bug: a character that cannot speak has lost a skill row.
    local common, orcish = 98, 109
    t.check("knows a racial language",
            player:HasSkill(common) or player:HasSkill(orcish),
            "common=" .. tostring(player:HasSkill(common))
                .. " orcish=" .. tostring(player:HasSkill(orcish)),
            "at least one")
end)
