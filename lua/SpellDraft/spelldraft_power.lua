--[[
    SpellDraft power snapshot push.

    Why this exists: the 3.3.5a client can only read the power pool of a unit's
    CURRENT power type (UnitMana/UnitManaMax; UnitPower/UnitPowerMax are 4.x API
    and this client has neither). A multiclass character therefore has a pool it
    can spend but cannot see - a Warrior with a drafted mana class, a Mage with a
    drafted rage class - and the HUD bars in SpellChoice.lua had no value to draw
    for them (they called UnitPower, which is nil here, so the bars never
    updated at all).

    The server knows every pool, so it pushes them: "0:cur:max;1:cur:max;..." for
    each power type the character actually has, in DISPLAY units - rage and runic
    power divided by 10, exactly like UnitMana reports them, so the addon's bars
    and the native bars read the same scale.

    Sent once after login and then once a second while anything changed; a
    character standing still with full pools sends nothing.
]]

local SD_POWER_PREFIX = "SpellDraftPower"
local SD_POWER_TYPES = { 0, 1, 3, 6 }   -- mana, rage, energy, runic power
local SD_POWER_POLL_MS = 1000

local powerLastPayload = {}
local powerTickerIds = {}

local function PowerIsBot(player)
    return player.IsBot ~= nil and player:IsBot()
end

-- Rage and runic power are stored x10; every WotLK UI shows them divided by 10.
local function PowerToDisplay(powerType, value)
    if powerType == 1 or powerType == 6 then
        return math.floor(value / 10)
    end
    return value
end

local function PowerBuildPayload(player)
    local parts = {}
    for _, powerType in ipairs(SD_POWER_TYPES) do
        local max = player:GetMaxPower(powerType) or 0
        if max > 0 then
            local cur = player:GetPower(powerType) or 0
            table.insert(parts, powerType .. ":" .. PowerToDisplay(powerType, cur)
                               .. ":" .. PowerToDisplay(powerType, max))
        end
    end
    return table.concat(parts, ";")
end

local function PowerPush(player)
    if PowerIsBot(player) or not player:IsInWorld() then return end

    local guid = player:GetGUIDLow()
    local payload = PowerBuildPayload(player)
    if payload == "" or payload == powerLastPayload[guid] then return end

    powerLastPayload[guid] = payload
    player:SendAddonMessage(SD_POWER_PREFIX, payload, 0, player)
end

-- One ticker per player: four power reads a second, and it covers every source
-- of change - regen ticks, spell costs, rage from damage, a class change, a
-- level-up - without hooking any of them individually.
local function PowerStartTicker(player)
    local guid = player:GetGUIDLow()
    if powerTickerIds[guid] then return end

    powerTickerIds[guid] = CreateLuaEvent(function()
        local p = GetPlayerByGUID(guid)
        if not p or not p:IsInWorld() then
            powerTickerIds[guid] = nil
            powerLastPayload[guid] = nil
            return
        end
        PowerPush(p)
    end, SD_POWER_POLL_MS, 0)
end

local function PowerOnLogin(_, player)
    local guid = player:GetGUIDLow()

    -- Delayed: the login-time pool seeding (mod-multiclass's ApplySecondaryClass
    -- and spelldraft_core's draft seeding) has to land first, or the first
    -- snapshot describes a character with no pools at all.
    CreateLuaEvent(function()
        local p = GetPlayerByGUID(guid)
        if p and p:IsInWorld() then
            PowerPush(p)
            PowerStartTicker(p)
        end
    end, 3000, 1)
end

local function PowerOnLogout(_, player)
    local guid = player:GetGUIDLow()
    powerLastPayload[guid] = nil
    if powerTickerIds[guid] then
        RemoveEventById(powerTickerIds[guid])
        powerTickerIds[guid] = nil
    end
end

RegisterPlayerEvent(3, PowerOnLogin)     -- PLAYER_EVENT_ON_LOGIN
RegisterPlayerEvent(4, PowerOnLogout)    -- PLAYER_EVENT_ON_LOGOUT
