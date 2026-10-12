local parts = redis.call('TIME')
local now = tonumber(parts[1]) * 1000 + math.floor(tonumber(parts[2]) / 1000)
local values = redis.call('HMGET', KEYS[1], 'state', 'version', 'entered_at_ms', 'expires_at_ms', 'reason_code', 'operation_id')
if not values[1] then
  return {'NORMAL', '0', '0', '0', 'none', 'none'}
end

local version = tonumber(values[2])
local entered = tonumber(values[3])
local expires = tonumber(values[4])
if (values[1] ~= 'SURGE' and values[1] ~= 'RECOVERY') or
   not version or version < 1 or version % 1 ~= 0 or
   not entered or entered < 1 or not expires or expires <= entered then
  return {'CORRUPT', '0', '0', '0', 'invalid_state', 'none'}
end

local state = values[1]
local effective_entered = entered
local effective_expires = expires
local reason = values[5] or 'unknown'
if state == 'SURGE' and now >= expires then
  state = 'RECOVERY'
  effective_entered = expires
  effective_expires = expires + tonumber(ARGV[1])
  reason = 'surge_expired'
elseif state == 'RECOVERY' and now >= expires then
  state = 'NORMAL'
  effective_entered = expires
  effective_expires = 0
  reason = 'recovery_elapsed'
end

return {state, tostring(version), tostring(effective_entered), tostring(effective_expires), reason, values[6] or 'none'}
