--[[
    B2 - hybrid resource pools.

    The claim under test: a character gets the UNION of both classes' pools, and
    mana is seeded for a primary class that has none (mod-multiclass's
    ApplyHybridMana, driven by Multiclass.HybridMana*).

    Deliberately does NOT change the character's level. The plan sketched
    measuring the per-level slope across two SetLevel calls, but SetLevel on a
    real character is far more destructive than this test is worth; the measured
    figures are reported with t.note instead, so a config change still shows up
    as a diff in the log rather than a silent pass.

    MUTATES the secondary class. Restored by a cleanup.
]]

SelfTest = SelfTest or {}
SelfTest.batteries = SelfTest.batteries or {}
SelfTest.order = SelfTest.order or {}
SelfTest.mutating = SelfTest.mutating or {}

local POWER_MANA = 0

local CLASS_MAGE, CLASS_WARLOCK = 8, 9

-- Classes whose own resource is rage, energy or runic power - these are the
-- ones where a mana secondary has something to prove.
local NO_NATIVE_MANA = { [1] = true, [4] = true, [6] = true }

local CLASS_COMMAND_NAME = {
    [1] = "warrior", [2] = "paladin", [3] = "hunter", [4] = "rogue", [5] = "priest",
    [6] = "deathknight", [7] = "shaman", [8] = "mage", [9] = "warlock", [11] = "druid",
}

SelfTest.register("hybrid_power", function(t, player)
    local primary = player:GetClass()
    local original = CONFIG.GetSecondaryClassId(player)

    t.cleanup(function(p)
        if original and original > 0 then
            p:RunCommand("multiclass choose " .. CLASS_COMMAND_NAME[original])
        else
            p:RunCommand("multiclass clear")
        end
    end)

    local caster = (primary ~= CLASS_MAGE) and CLASS_MAGE or CLASS_WARLOCK

    t.section("baseline")

    player:RunCommand("multiclass clear")
    local baseMana = player:GetMaxPower(POWER_MANA)
    t.note("max mana with no secondary class", baseMana)
    t.note("primary class", primary)
    t.note("level", player:GetLevel())

    t.section("mana from a caster secondary")

    player:RunCommand("multiclass choose " .. CLASS_COMMAND_NAME[caster])
    local hybridMana = player:GetMaxPower(POWER_MANA)
    t.note("max mana with a caster secondary", hybridMana)

    if NO_NATIVE_MANA[primary] then
        -- The interesting case: the primary brings no mana at all, so every
        -- point of it came from the secondary class.
        t.check("primary with no native mana starts at zero", baseMana == 0,
                baseMana, 0)
        t.check("caster secondary grants a mana pool", hybridMana > 0,
                hybridMana, "> 0")

        -- A pool that exists but is empty is a pool no spell can be paid from:
        -- this is the half that used to be missing (max seeded, current left at
        -- zero), and it is why a Warrior who drafted a mana class could not cast.
        t.check("caster secondary fills the mana pool",
                player:GetPower(POWER_MANA) == hybridMana,
                player:GetPower(POWER_MANA), hybridMana)

        -- And it has to keep refilling: for a class without native mana the
        -- engine's own spirit regen is `spirit * gtRegenMPPerSpt[class]`, whose
        -- per-class row is zero, so mod-multiclass applies a mana-per-5 bonus.
        -- UNIT_FIELD_POWER_REGEN_FLAT_MODIFIER is OBJECT_END (6) + 0x22, and the
        -- POWER_MANA slot is +0 (UpdateFields.h).
        local REGEN_FIELD_MANA = 6 + 0x22
        local regen = player:GetFloatValue(REGEN_FIELD_MANA)
        t.check("hybrid mana regenerates", regen > 0, regen, "> 0")
    else
        -- A caster primary already has mana; the secondary must not take it away.
        t.check("caster primary keeps its mana pool", baseMana > 0, baseMana, "> 0")
        t.check("secondary class does not reduce the mana pool",
                hybridMana >= baseMana, hybridMana, ">= " .. tostring(baseMana))
    end

    t.section("the pool goes away again")

    player:RunCommand("multiclass clear")
    local clearedMana = player:GetMaxPower(POWER_MANA)
    t.assert_eq("mana returns to its baseline after clearing", clearedMana, baseMana)
end, { mutates = true, requires = "traditional" })
