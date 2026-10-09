"""Budget ledger Lua scripts (atomic reserve / release / commit).

Extracted from ``budget_ledger.py`` (pure move, no behavior change);
``app.core.budget_ledger`` remains the public facade.
"""
from __future__ import annotations



# ── Lua scripts ──────────────────────────────────────────────────────
#
# Every mutating operation runs inside Lua so the check → mutation
# sequence cannot interleave with a concurrent operation. Redis
# scripting is single-threaded per node.

# KEYS: reserved, committed, res_hash, ready
# ARGV: reservation_id, estimated, cap, ttl
_RESERVE_SCRIPT = """
if redis.call('EXISTS', KEYS[4]) == 0 then
    return {-1, 0, 0}
end
local reservation_id = ARGV[1]
local estimated = tonumber(ARGV[2])
local cap = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local reserved = tonumber(redis.call('GET', KEYS[1]) or '0')
local committed = tonumber(redis.call('GET', KEYS[2]) or '0')

if reserved + committed + estimated > cap then
    return {0, reserved, committed}
end

redis.call('HSET', KEYS[3], reservation_id, estimated)
redis.call('EXPIRE', KEYS[3], ttl)
local new_reserved = redis.call('INCRBY', KEYS[1], estimated)
redis.call('EXPIRE', KEYS[1], ttl)
redis.call('EXPIRE', KEYS[2], ttl)
return {1, new_reserved, committed}
"""


# KEYS: reserved, res_hash
# ARGV: reservation_id, ttl
_RELEASE_SCRIPT = """
local reservation_id = ARGV[1]
local ttl = tonumber(ARGV[2])

local amount = tonumber(redis.call('HGET', KEYS[2], reservation_id) or '0')
if amount == 0 then
    return 0
end
redis.call('HDEL', KEYS[2], reservation_id)
local new_val = redis.call('DECRBY', KEYS[1], amount)
if new_val <= 0 then
    redis.call('DEL', KEYS[1])
else
    -- Preserve the counter's TTL — a partial refund must not turn a
    -- period-scoped counter into a leaked-forever key.
    redis.call('EXPIRE', KEYS[1], ttl)
end
return amount
"""


# KEYS: reserved, committed, res_hash
# ARGV: reservation_id, actual, ttl
_COMMIT_SCRIPT = """
local reservation_id = ARGV[1]
local actual = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

local estimated = tonumber(redis.call('HGET', KEYS[3], reservation_id) or '0')
if estimated == 0 then
    return 0
end
redis.call('HDEL', KEYS[3], reservation_id)
local new_reserved = redis.call('DECRBY', KEYS[1], estimated)
if new_reserved <= 0 then
    redis.call('DEL', KEYS[1])
else
    redis.call('EXPIRE', KEYS[1], ttl)
end
redis.call('INCRBY', KEYS[2], actual)
redis.call('EXPIRE', KEYS[2], ttl)
return 1
"""
