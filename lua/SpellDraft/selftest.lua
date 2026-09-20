--[[
    SpellDraft / mod-multiclass self-test harness.

    The multiclass feature is asserted from HERE rather than from the Go e2e
    suite, because Eluna is the only layer that can see the state that matters:
    AzerothGhost has no talent, spellbook, skill or power query at all, while
    Eluna exposes HasSpell / HasTalent / HasSkill / GetSkillValue / GetPower /
    GetMaxPower / RunCommand. The Go side's only job is to log a character in so
    a battery has a subject to run against.

    Output is one line per assertion, to the worldserver log, in a shape
    tools/run_selftest.py parses:

        [SDTEST] RUN|start|char=<name>|batteries=<n>
        [SDTEST] PASS|<battery>|<assertion>|got=<x>|want=<y>
        [SDTEST] FAIL|<battery>|<assertion>|got=<x>|want=<y>
        [SDTEST] SUMMARY|pass=<n>|fail=<n>|battery=<name>
        [SDTEST] RUN|end|pass=<n>|fail=<n>|batteries=<n>

    Batteries live in SpellDraft/selftest/ and self-register:

        SelfTest.register("multiclass_identity", function(t, player)
            t.assert_eq("secondary class", CONFIG.GetSecondaryClassId(player), 8)
        end, { mutates = true })

    A battery MUST leave the character as it found it. Use t.cleanup(fn) to push
    a restore step; cleanups run in reverse order after the battery finishes,
    including when it errors.

    Anything that changes the character declares { mutates = true }, and is then
    left out of a bare run - the character is usually a real one, and a restore
    is only as good as the battery reaching the end. To include them:

        SD_SELFTEST                 read-only batteries (safe on any character)
        SD_SELFTEST all             every battery, mutations included
        SD_SELFTEST <battery>       just that one, mutating or not

    Disabled by default (CONFIG.SELFTEST_ENABLED). Nothing in this file touches a
    player, registers a hook side effect, or prints anything while it is off.
]]

-- Created defensively so load order between this file and the batteries in
-- SpellDraft/selftest/ cannot matter - whichever is compiled first wins.
SelfTest = SelfTest or {}
SelfTest.batteries = SelfTest.batteries or {}
SelfTest.order = SelfTest.order or {}

local PREFIX = "[SDTEST] "

local function enabled()
    return CONFIG and CONFIG.SELFTEST_ENABLED == true
end

-- Values land in a pipe-delimited log line, so anything that would break the
-- record separator is flattened rather than escaped - these are diagnostics,
-- not data we ever need to round-trip.
local function fmt(value)
    if value == nil then return "nil" end
    if type(value) == "boolean" then return value and "true" or "false" end
    local text = tostring(value)
    text = text:gsub("[\r\n]+", " ")
    text = text:gsub("|", "/")
    return text
end

-- opts.mutates marks a battery that changes the character it runs on (secondary
-- class, level, bags, talents). Those are EXCLUDED from a bare run, because the
-- character on the other end is usually a real one somebody cares about and a
-- restore is only as good as the battery finishing. Ask for them by name, or
-- with `SD_SELFTEST all`.
SelfTest.mutating = SelfTest.mutating or {}

-- opts.requires = "traditional" marks a battery whose assumptions only hold for
-- a non-draft character. Draft mode is a different game: spelldraft_talents.lua
-- resets talents and forces native free talent points to 0 on every login, the
-- custom pool lives in prestige_stats.talent_points instead, and power is
-- seeded independently of class - so "a Rogue has no mana" is simply untrue
-- there. Such a battery is skipped, loudly, rather than reporting a false fail.
SelfTest.requires = SelfTest.requires or {}

function SelfTest.register(name, fn, opts)
    if SelfTest.batteries[name] == nil then
        table.insert(SelfTest.order, name)
    end
    SelfTest.batteries[name] = fn
    SelfTest.mutating[name] = (opts ~= nil and opts.mutates == true)
    SelfTest.requires[name] = opts and opts.requires or nil
end

-- The same query the four local IsInDraftMode/IsPlayerInDraft copies use
-- (spelldraft_talents.lua:7 and friends); none of them is reachable from here.
function SelfTest.isInDraftMode(player)
    local result = CharDBQuery(
        "SELECT draft_state FROM prestige_stats WHERE player_id = " .. player:GetGUIDLow())
    return result ~= nil and result:GetUInt32(0) == 1
end

-- One battery's recording context: counters, cleanup stack, assertion helpers.
local function newContext(battery)
    local t = { battery = battery, pass = 0, fail = 0, cleanups = {} }

    local function emit(result, assertion, got, want)
        if result == "PASS" then t.pass = t.pass + 1 else t.fail = t.fail + 1 end
        print(PREFIX .. result .. "|" .. battery .. "|" .. fmt(assertion)
              .. "|got=" .. fmt(got) .. "|want=" .. fmt(want))
    end

    function t.assert_eq(assertion, got, want)
        emit(got == want and "PASS" or "FAIL", assertion, got, want)
        return got == want
    end

    function t.assert_true(assertion, got)
        return t.assert_eq(assertion, got and true or false, true)
    end

    function t.assert_false(assertion, got)
        return t.assert_eq(assertion, got and true or false, false)
    end

    -- For assertions with no single expected value (ranges, tolerances). The
    -- caller decides; this just records the verdict and the observed figure.
    function t.check(assertion, ok, got, want)
        emit(ok and "PASS" or "FAIL", assertion, got, want or "-")
        return ok and true or false
    end

    -- A measurement worth seeing in the log even though nothing asserts on it,
    -- so a config change shows up as a diff rather than a silent pass.
    function t.note(assertion, got)
        print(PREFIX .. "NOTE|" .. battery .. "|" .. fmt(assertion)
              .. "|got=" .. fmt(got) .. "|want=-")
    end

    function t.cleanup(fn)
        table.insert(t.cleanups, fn)
    end

    function t.section(name)
        print(PREFIX .. "SECTION|" .. battery .. "|" .. fmt(name) .. "|got=-|want=-")
    end

    return t
end

local function runCleanups(t, player)
    for i = #t.cleanups, 1, -1 do
        local ok, err = pcall(t.cleanups[i], player)
        if not ok then
            t.fail = t.fail + 1
            print(PREFIX .. "FAIL|" .. t.battery .. "|cleanup #" .. i
                  .. "|got=" .. fmt(err) .. "|want=no error")
        end
    end
end

local function runBattery(name, player)
    local fn = SelfTest.batteries[name]
    local t = newContext(name)

    if SelfTest.requires[name] == "traditional" and SelfTest.isInDraftMode(player) then
        print(PREFIX .. "SKIP|" .. name
              .. "|needs a non-draft character|got=draft_state=1|want=traditional")
        print(PREFIX .. "SUMMARY|pass=0|fail=0|battery=" .. name)
        return 0, 0
    end

    if type(fn) ~= "function" then
        t.fail = 1
        print(PREFIX .. "FAIL|" .. name .. "|battery is registered|got="
              .. fmt(type(fn)) .. "|want=function")
    else
        -- pcall so one broken battery cannot take down a real player's login.
        local ok, err = pcall(fn, t, player)
        if not ok then
            t.fail = t.fail + 1
            print(PREFIX .. "FAIL|" .. name .. "|battery ran without error|got="
                  .. fmt(err) .. "|want=no error")
        end
        runCleanups(t, player)
    end

    print(PREFIX .. "SUMMARY|pass=" .. t.pass .. "|fail=" .. t.fail .. "|battery=" .. name)
    return t.pass, t.fail
end

-- Runs every registered battery, or just `only` when given.
function SelfTest.run(player, only)
    if not enabled() then return end
    if not player or not player:IsInWorld() then return end

    local names = {}
    local skipped = 0
    if only == "all" then
        names = SelfTest.order
    elseif only and only ~= "" then
        if SelfTest.batteries[only] == nil then
            print(PREFIX .. "RUN|error|unknown battery=" .. fmt(only))
            return
        end
        names = { only }
    else
        for _, name in ipairs(SelfTest.order) do
            if SelfTest.mutating[name] then
                skipped = skipped + 1
            else
                table.insert(names, name)
            end
        end
    end

    if skipped > 0 then
        print(PREFIX .. "RUN|note|skipped " .. skipped
              .. " mutating batteries, run `SD_SELFTEST all` to include them")
    end

    print(PREFIX .. "RUN|start|char=" .. fmt(player:GetName()) .. "|batteries=" .. #names)

    local pass, fail = 0, 0
    for _, name in ipairs(names) do
        local p, f = runBattery(name, player)
        pass, fail = pass + p, fail + f
    end

    print(PREFIX .. "RUN|end|pass=" .. pass .. "|fail=" .. fail .. "|batteries=" .. #names)
end

---------------------------------------------------------------------------
-- Triggers
---------------------------------------------------------------------------

-- Login: only for characters named for the rig, and deliberately delayed. At
-- PLAYER_EVENT_ON_LOGIN the character is not settled enough for power and
-- talent figures to be meaningful, and spelldraft_core's own first-login grants
-- are still landing.
local function OnLogin(event, player)
    if not enabled() then return end

    local prefix = CONFIG.SELFTEST_NAME_PREFIX
    if not prefix or prefix == "" then return end

    local name = player:GetName() or ""
    if name:sub(1, #prefix):lower() ~= prefix:lower() then return end

    local guid = player:GetGUIDLow()
    CreateLuaEvent(function()
        local p = GetPlayerByGUID(guid)
        if p and p:IsInWorld() then
            SelfTest.run(p)
        end
    end, 3000, 1)
end

-- Whisper-to-self: `SD_SELFTEST` runs everything, `SD_SELFTEST <name>` runs one.
-- Registered as its own handler rather than folded into spell_choice.lua's
-- OnAddonWhisper, which filters to the "SC" namespace and must stay untouched;
-- this mirrors how spelldraft_re.lua owns the "SDRE_" namespace.
local function OnSelfTestWhisper(event, player, msg, msgType, lang, receiver)
    if not enabled() then return end
    if CONFIG.SELFTEST_ALLOW_WHISPER ~= true then return end
    if type(msg) ~= "string" or msg:sub(1, 11) ~= "SD_SELFTEST" then return end

    local only = msg:match("^SD_SELFTEST%s+(%S+)$")
    local guid = player:GetGUIDLow()
    CreateLuaEvent(function()
        local p = GetPlayerByGUID(guid)
        if p and p:IsInWorld() then
            SelfTest.run(p, only)
        end
    end, 100, 1)

    return false  -- swallow it, so the trigger never shows up in chat
end

RegisterPlayerEvent(3, OnLogin)
RegisterPlayerEvent(19, OnSelfTestWhisper)

-- CONFIG does not exist yet while this file is executing. ALE sorts scripts by
-- full filepath (LuaEngine.cpp's ScriptPathComparator) and "SpellDraft/" sorts
-- before "spelldraft_config.lua" on the capital S, so every file in this folder
-- runs before the config does. Measured, not assumed: a probe here logged
-- "CONFIG visible at load = false" while a deferred event 1s later saw it fine.
--
-- So: no CONFIG read at file scope, here or in any battery. Read it inside a
-- handler or a CreateLuaEvent, both of which run long after load.
CreateLuaEvent(function()
    if not enabled() then return end
    print("[SpellDraft] self-test rig ENABLED (login prefix '"
          .. tostring(CONFIG.SELFTEST_NAME_PREFIX)
          .. "', whisper SD_SELFTEST to run). Batteries registered: "
          .. #SelfTest.order .. " [" .. table.concat(SelfTest.order, ", ") .. "].")
end, 1000, 1)
