--[[
    B1 - secondary class selection and identity.

    Drives the `.multiclass` command through Eluna's RunCommand, which is the
    only non-interactive way in: the command is declared SEC_PLAYER and
    Console::No (modules/mod-multiclass/src/multiclass_command.cpp), so SOAP and
    RA cannot reach it. That is also why this battery lives here rather than in
    the Go suite.

    MUTATES the character's secondary class. The original is captured first and
    restored by a cleanup, which runs even if the battery errors partway.
]]

SelfTest = SelfTest or {}
SelfTest.batteries = SelfTest.batteries or {}
SelfTest.order = SelfTest.order or {}
SelfTest.mutating = SelfTest.mutating or {}

local CLASS_WARRIOR, CLASS_MAGE, CLASS_WARLOCK, CLASS_DEATH_KNIGHT = 1, 8, 9, 6

local CLASS_COMMAND_NAME = {
    [1] = "warrior", [2] = "paladin", [3] = "hunter", [4] = "rogue", [5] = "priest",
    [6] = "deathknight", [7] = "shaman", [8] = "mage", [9] = "warlock", [11] = "druid",
}

-- A secondary class that is guaranteed not to be the character's primary, and
-- that brings mana with it so B2 can lean on the same choice.
local function pickSecondary(primary)
    if primary ~= CLASS_MAGE then return CLASS_MAGE end
    return CLASS_WARLOCK
end

local function choose(player, classId)
    player:RunCommand("multiclass choose " .. CLASS_COMMAND_NAME[classId])
end

SelfTest.register("multiclass_identity", function(t, player)
    local primary = player:GetClass()
    local original = CONFIG.GetSecondaryClassId(player)

    -- Pushed before anything is changed, so an error at any point below still
    -- puts the character back the way it was found.
    t.cleanup(function(p)
        if original and original > 0 then
            choose(p, original)
        else
            p:RunCommand("multiclass clear")
        end
    end)

    t.section("choose a secondary class")

    local wanted = pickSecondary(primary)
    choose(player, wanted)
    t.assert_eq("chosen class is stored", CONFIG.GetSecondaryClassId(player), wanted)
    t.assert_true("class set now contains the secondary",
                  CONFIG.GetPlayerClassSet(player)[wanted] == true)
    t.assert_true("class set still contains the primary",
                  CONFIG.GetPlayerClassSet(player)[primary] == true)

    t.section("invalid choices are refused")

    -- The command rejects the primary class explicitly ("... is already your
    -- primary class"), so the stored value must be untouched afterwards.
    choose(player, primary)
    t.assert_eq("primary class refused as secondary",
                CONFIG.GetSecondaryClassId(player), wanted)

    -- Assumes the shipped default Multiclass.AllowDeathKnightSecondary = 0. If
    -- that option is ever turned on, this assertion is the thing that should
    -- change, not the module.
    if primary ~= CLASS_DEATH_KNIGHT then
        choose(player, CLASS_DEATH_KNIGHT)
        t.assert_eq("death knight refused as secondary (default config)",
                    CONFIG.GetSecondaryClassId(player), wanted)
    end

    t.section("clear")

    player:RunCommand("multiclass clear")
    t.assert_eq("clear removes the secondary class",
                CONFIG.GetSecondaryClassId(player), 0)
    t.assert_true("class set falls back to the primary alone",
                  CONFIG.GetPlayerClassSet(player)[primary] == true)
    t.assert_false("cleared secondary is gone from the class set",
                   CONFIG.GetPlayerClassSet(player)[wanted] == true)

    t.section("re-choosing after a clear")

    choose(player, wanted)
    t.assert_eq("secondary class can be set again after clearing",
                CONFIG.GetSecondaryClassId(player), wanted)
end, { mutates = true, requires = "traditional" })
