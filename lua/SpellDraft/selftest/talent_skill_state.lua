--[[
    B3 - talent points, proficiencies, and the language regression guard.

    The language check is the one assertion that must hold; the talent-point half is
    deliberately a MEASUREMENT. Multiclass.TalentPointMultiplier is applied through
    the OnPlayerCalculateTalentsPoints hook, which the core only calls from
    Player::InitTalentForLevel - and changing the secondary class does not call
    it (mod-multiclass's ApplySecondaryClass only grants proficiencies and mana).
    So the pool may well not refresh until a level change or a relog. Rather
    than assert a doubling that might legitimately not have happened yet, this
    records both figures so the log shows whether it refreshes live.

    The proficiency half asserts the per-class contract (P5.1/P5.2) instead of the
    blanket grant it replaced: the union of the two classes' own weapon/armour lines
    must be known - read from playercreateinfo_skills, the same table the module
    reads - and a secondary class that is dropped must not leave its lines behind.
    Lines left over from the pre-P5.1 blanket grant are reported, not asserted on:
    `.multiclass sync` is the command that removes those.

    MUTATES the secondary class. Restored by a cleanup.
]]

SelfTest = SelfTest or {}
SelfTest.batteries = SelfTest.batteries or {}
SelfTest.order = SelfTest.order or {}
SelfTest.mutating = SelfTest.mutating or {}

local CLASS_MAGE, CLASS_WARLOCK = 8, 9

local CLASS_COMMAND_NAME = {
    [1] = "warrior", [2] = "paladin", [3] = "hunter", [4] = "rogue", [5] = "priest",
    [6] = "deathknight", [7] = "shaman", [8] = "mage", [9] = "warlock", [11] = "druid",
}

-- Every spoken language in 3.3.5a. A character must know at least one, or it
-- cannot talk at all - see the Blood Elf bug this guards against.
local LANGUAGE_SKILLS = {
    { id = 98,  name = "Common" },     { id = 109, name = "Orcish" },
    { id = 111, name = "Dwarvish" },   { id = 113, name = "Darnassian" },
    { id = 115, name = "Taurahe" },    { id = 313, name = "Gnomish" },
    { id = 315, name = "Troll" },      { id = 673, name = "Gutterspeak" },
    { id = 137, name = "Thalassian" }, { id = 759, name = "Draenei" },
}

-- The item proficiency skill lines mod-multiclass can grant (weapon + armour).
-- Kept in sync with _proficiencySkills in
-- modules/mod-multiclass/src/multiclass_identity.cpp.
local PROFICIENCY_SKILLS = {
    { id = 43,  name = "Swords" },   { id = 44,  name = "Axes" },
    { id = 45,  name = "Bows" },     { id = 46,  name = "Guns" },
    { id = 54,  name = "Maces" },    { id = 55,  name = "2H Swords" },
    { id = 136, name = "Staves" },   { id = 160, name = "2H Maces" },
    { id = 172, name = "2H Axes" },  { id = 173, name = "Daggers" },
    { id = 176, name = "Thrown" },   { id = 226, name = "Crossbows" },
    { id = 228, name = "Wands" },    { id = 229, name = "Polearms" },
    { id = 293, name = "Plate" },    { id = 413, name = "Mail" },
    { id = 414, name = "Leather" },  { id = 415, name = "Cloth" },
    { id = 433, name = "Shield" },   { id = 473, name = "Fist Weapons" },
}

local PROFICIENCY_NAMES = {}
for _, entry in ipairs(PROFICIENCY_SKILLS) do
    PROFICIENCY_NAMES[entry.id] = entry.name
end

-- 2^(bit-1) without a bitwise operator: mod-ale's shipped default Lua version
-- (LUA_VERSION=lua52) predates Lua's `<<`/`&`, and the rest of this module avoids
-- them for the same reason.
local function bit_mask(bit)
    local mask = 1
    for _ = 2, bit do
        mask = mask * 2
    end
    return mask
end

-- The proficiency lines one class gives this character's race, read from the same
-- table the module reads (PlayerInfo::skills is playercreateinfo_skills filtered by
-- the core's race/class masks). Only the proficiency domain is kept, matching the
-- module's allowlist.
local function class_proficiencies(player, classId)
    local set = {}
    if not classId or classId <= 0 then
        return set
    end

    local raceMask = bit_mask(player:GetRace())
    local classMask = bit_mask(classId)
    local query = WorldDBQuery(
        "SELECT skill FROM playercreateinfo_skills WHERE (raceMask = 0 OR (raceMask & "
        .. raceMask .. ")) AND (classMask = 0 OR (classMask & " .. classMask .. "))")

    if query then
        repeat
            local skill = query:GetUInt32(0)
            if PROFICIENCY_NAMES[skill] then
                set[skill] = true
            end
        until not query:NextRow()
    end

    return set
end

local function union(into, from)
    for skill in pairs(from) do
        into[skill] = true
    end
    return into
end

local function join_skills(set)
    local names = {}
    for skill in pairs(set) do
        table.insert(names, PROFICIENCY_NAMES[skill] or tostring(skill))
    end
    table.sort(names)
    return (#names > 0) and table.concat(names, ",") or "none"
end

local function count_keys(set)
    local n = 0
    for _ in pairs(set) do
        n = n + 1
    end
    return n
end

SelfTest.register("talent_skill_state", function(t, player)
    local original = CONFIG.GetSecondaryClassId(player)
    local primary = player:GetClass()

    t.cleanup(function(p)
        if original and original > 0 then
            p:RunCommand("multiclass choose " .. CLASS_COMMAND_NAME[original])
        else
            p:RunCommand("multiclass clear")
        end
    end)

    t.section("spoken language (regression guard)")

    -- This is the assertion that matters most in this battery. A character with
    -- no language skill row cannot use say/yell or any GM dot-command sent as
    -- Say, which is exactly how the Blood Elf case was first noticed.
    local known = {}
    for _, lang in ipairs(LANGUAGE_SKILLS) do
        if player:HasSkill(lang.id) then
            table.insert(known, lang.name)
        end
    end
    t.check("character knows at least one spoken language", #known > 0,
            (#known > 0) and table.concat(known, "+") or "none", "at least one")
    t.note("languages known", (#known > 0) and table.concat(known, "+") or "none")

    -- The lines the outgoing secondary class used to add, captured before the class
    -- changes below so the same battery can check they are taken back: mod-multiclass
    -- revokes the pair delta on clear/choose (P5.2).
    local originalLines = class_proficiencies(player, original)
    t.note("outgoing secondary class lines", join_skills(originalLines))

    t.section("talent point pool")

    player:RunCommand("multiclass clear")
    local freeSingle = player:GetFreeTalentPoints()
    t.note("free talent points, single class", freeSingle)

    local secondary = (primary ~= CLASS_MAGE) and CLASS_MAGE or CLASS_WARLOCK
    player:RunCommand("multiclass choose " .. CLASS_COMMAND_NAME[secondary])
    local freeDual = player:GetFreeTalentPoints()
    t.note("free talent points, with a secondary class", freeDual)
    t.note("difference", freeDual - freeSingle)

    -- Weak on purpose: see the header. The strong version of this belongs in a
    -- battery that can force InitTalentForLevel, or that runs across a relog.
    t.check("talent point pool did not shrink when a class was added",
            freeDual >= freeSingle, freeDual, ">= " .. tostring(freeSingle))

    t.section("class-pair proficiencies")

    -- P5.1: the module grants the union of the two classes' own proficiency lines,
    -- read from playercreateinfo_skills. Multiclass.GrantClassProficiencies fires
    -- for a character with a secondary class, so this runs while one is set (above).
    local expected = union(class_proficiencies(player, primary),
                           class_proficiencies(player, secondary))
    local missing = {}
    for skill in pairs(expected) do
        if not player:HasSkill(skill) then
            table.insert(missing, PROFICIENCY_NAMES[skill] or tostring(skill))
        end
    end
    t.check("class-pair proficiency lines are known", #missing == 0,
            (#missing == 0) and join_skills(expected) or ("missing " .. table.concat(missing, ",")),
            join_skills(expected))

    -- P5.2: a class that was dropped cannot leave its lines behind. Anything the
    -- outgoing class had that neither the primary class nor the new secondary class
    -- grants must be gone - the module keeps only what the pair legitimately has.
    local leftover = {}
    for skill in pairs(originalLines) do
        if not expected[skill] and player:HasSkill(skill) then
            table.insert(leftover, PROFICIENCY_NAMES[skill] or tostring(skill))
        end
    end
    t.check("dropping a secondary class takes its proficiency lines back",
            #leftover == 0,
            (#leftover == 0) and "none" or table.concat(leftover, ","),
            "none")
    t.note("revocation check",
           (count_keys(originalLines) > 0) and "ran" or "no secondary class to drop")

    -- Leftovers from the pre-P5.1 blanket grant are reported, not asserted on: an
    -- existing character keeps them until someone runs .multiclass sync.
    local outside = {}
    for _, entry in ipairs(PROFICIENCY_SKILLS) do
        if player:HasSkill(entry.id) and not expected[entry.id] then
            table.insert(outside, entry.name)
        end
    end
    t.note("proficiency lines outside the class pair (use .multiclass sync)",
           (#outside > 0) and table.concat(outside, ",") or "none")

    for _, entry in ipairs(PROFICIENCY_SKILLS) do
        if player:HasSkill(entry.id) then
            t.note(entry.name .. " skill value", player:GetSkillValue(entry.id))
        end
    end
end, { mutates = true, requires = "traditional" })
