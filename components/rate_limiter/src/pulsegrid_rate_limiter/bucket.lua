-- All reads, types, stored configuration and decisions precede writes.
-- Dedicated standalone Redis only. Every accessed key is passed in KEYS.
local n = #KEYS
local maxint = 9007199254740991
if n < 1 or n > 3 or #ARGV ~= n * 4 then return redis.error_reply('INVALID_BUCKETS') end
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local rows = {}
local retry = 0
local remaining = maxint
for i = 1,n do
  for j = 1,i-1 do
    if KEYS[i] == KEYS[j] then return redis.error_reply('DUPLICATE_BUCKET') end
  end
  local a = (i-1)*4
  local cap = tonumber(ARGV[a+1])
  local rate = tonumber(ARGV[a+2])
  local cost = tonumber(ARGV[a+3])
  local ttl = tonumber(ARGV[a+4])
  if not cap or not rate or not cost or not ttl or cap < 1000 or rate < 1 or cost < 1000
     or cost > cap or cap % 1000 ~= 0 or cost % 1000 ~= 0
     or rate % 1 ~= 0 or ttl % 1 ~= 0 or ttl > maxint
     or cap*1000 + rate + 999 > maxint then
    return redis.error_reply('INVALID_CONFIG')
  end
  local fill = math.ceil(cap*1000/rate)
  if fill*rate+999 > maxint or ttl < fill+1000 then return redis.error_reply('INVALID_TTL') end
  local typ = redis.call('TYPE', KEYS[i]).ok
  if typ ~= 'none' and typ ~= 'hash' then return redis.error_reply('INVALID_TYPE') end
  local tokens, last, carry = cap, now, 0
  if typ == 'hash' then
    local old = redis.call('HMGET', KEYS[i], 'tokens', 'last', 'carry', 'cap', 'rate', 'ttl')
    tokens, last, carry = tonumber(old[1]), tonumber(old[2]), tonumber(old[3])
    if not tokens or not last or not carry or tokens < 0 or tokens > cap or tokens%1 ~= 0
       or last < 0 or last > maxint or last%1 ~= 0 or carry < 0 or carry > 999 or carry%1 ~= 0
       or tonumber(old[4]) ~= cap or tonumber(old[5]) ~= rate or tonumber(old[6]) ~= ttl then
      return redis.error_reply('INVALID_STATE')
    end
    local elapsed = math.min(fill, math.max(0, now-last))
    local credit = elapsed*rate + carry
    tokens = math.min(cap, tokens + math.floor(credit/1000))
    carry = credit % 1000
    if tokens == cap then carry = 0 end
    -- Clock rollback does not earn the same interval twice.
    last = math.max(last, now)
  end
  local wait = math.max(0, math.ceil(((cost-tokens)*1000-carry)/rate))
  retry = math.max(retry, wait)
  rows[i] = {tokens=tokens, last=last, carry=carry, cap=cap, rate=rate, ttl=ttl, cost=cost}
end
local allowed = retry == 0
for i = 1,n do
  local r = rows[i]
  if allowed then r.tokens = r.tokens-r.cost end
  remaining = math.min(remaining, r.tokens)
end
-- A denied request needs no writes: next read computes credit from last state.
if allowed then
  for i = 1,n do
    local r = rows[i]
    redis.call('HSET', KEYS[i], 'tokens', r.tokens, 'last', r.last, 'carry', r.carry,
               'cap', r.cap, 'rate', r.rate, 'ttl', r.ttl)
    redis.call('PEXPIRE', KEYS[i], r.ttl)
  end
end
return {allowed and 1 or 0, retry, remaining}
