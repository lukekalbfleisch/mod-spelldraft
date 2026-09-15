-- The one EQ-pack talent that isn't a pure native SpellMod (see
-- tools/eq_talent_pack.json for why: buffing a summoned Guardian's own
-- stats isn't reachable through the caster-side SpellMod system, verified
-- against src/server/game/Spells/SpellEffects.cpp's EffectSummonType).
--
-- Skeletal Champion (talent marker spell 994020) buffs the Cavorting Bones
-- skeleton (creature 11200) directly on spawn if its owner knows the marker.

local SKELETON_ENTRY = 11200
local MARKER_SPELL = 994020
local BUFF_SPELL = 994090

RegisterCreatureEvent(SKELETON_ENTRY, 5, function(_, creature) -- CREATURE_EVENT_ON_SPAWN
    local owner = creature:GetOwner()
    if owner and owner:HasAura(MARKER_SPELL) then
        creature:CastSpell(creature, BUFF_SPELL, true)
    end
end)
