local function read_state(key, recovery_ms, now)
  local values = redis.call('HMGET', key, 'state', 'version', 'entered_at_ms', 'expires_at_ms', 'reason_code', 'operation_id')
  if not values[1] then
    return 'NORMAL', 0, 0, 0, 'none', 'none'
  end
  local version = tonumber(values[2])
  local entered = tonumber(values[3])
  local expires = tonumber(values[4])
  if (values[1] ~= 'SURGE' and values[1] ~= 'RECOVERY') or
     not version or version < 1 or version % 1 ~= 0 or
     not entered or entered < 1 or not expires or expires <= entered then
    return 'CORRUPT', 0, 0, 0, 'invalid_state', 'none'
  end
  local state = values[1]
  local effective_entered = entered
  local effective_expires = expires
  local reason = values[5] or 'unknown'
  if state == 'SURGE' and now >= expires then
    state = 'RECOVERY'
    effective_entered = expires
    effective_expires = expires + recovery_ms
    reason = 'surge_expired'
  elseif state == 'RECOVERY' and now >= expires then
    state = 'NORMAL'
    effective_entered = expires
    effective_expires = 0
    reason = 'recovery_elapsed'
  end
  return state, version, effective_entered, effective_expires, reason, values[6] or 'none'
end

local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local recovery_ms = tonumber(ARGV[12])
local state, version, entered, expires, reason, operation_id = read_state(KEYS[1], recovery_ms, now)
if state == 'CORRUPT' then
  return {'corrupt', state, state, tostring(version), tostring(now), '0', reason}
end

local expected_version = tonumber(ARGV[1])
local expected_state = ARGV[2]
local target = ARGV[3]
local override = ARGV[7] == '1'
if not expected_version or expected_version ~= version or expected_state ~= state then
  return {'conflict', state, state, tostring(version), tostring(now), tostring(expires), reason}
end
if target ~= 'SURGE' and target ~= 'RECOVERY' then
  return {'invalid', state, state, tostring(version), tostring(now), tostring(expires), 'invalid_target'}
end
if target == state then
  return {'noop', state, state, tostring(version), tostring(now), tostring(expires), reason}
end
if target == 'RECOVERY' and state ~= 'SURGE' then
  return {'noop', state, state, tostring(version), tostring(now), tostring(expires), reason}
end
if target == 'SURGE' and state == 'RECOVERY' and now - entered < tonumber(ARGV[9]) and not override then
  return {'cooldown', state, state, tostring(version), tostring(now), tostring(entered + tonumber(ARGV[9])), 'recovery_cooldown'}
end
if target == 'RECOVERY' and state == 'SURGE' and now - entered < tonumber(ARGV[8]) and not override then
  return {'cooldown', state, state, tostring(version), tostring(now), tostring(entered + tonumber(ARGV[8])), 'surge_cooldown'}
end

local new_version = version + 1
local ttl = target == 'SURGE' and tonumber(ARGV[10]) or tonumber(ARGV[11])
local new_expires = now + ttl
redis.call('HSET', KEYS[1],
  'state', target,
  'version', tostring(new_version),
  'entered_at_ms', tostring(now),
  'expires_at_ms', tostring(new_expires),
  'reason_code', ARGV[4],
  'operation_id', ARGV[5],
  'actor_digest', ARGV[6])
return {'applied', state, target, tostring(new_version), tostring(now), tostring(new_expires), ARGV[4]}
