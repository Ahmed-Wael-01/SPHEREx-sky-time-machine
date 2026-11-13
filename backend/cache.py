"""
Tiny cache wrapper: Redis when REDIS_URL is set and reachable, otherwise an in-process dict.

    from cache import cache
    value = cache.get_or_set("key", lambda: expensive(), ttl=3600)

Values must be JSON-serialisable (they are stored as JSON in Redis).
"""
from __future__ import annotations

import json
import os
import time


class _Memory:
    kind = "memory"

    def __init__(self):
        self._d = {}

    def get(self, key):
        v = self._d.get(key)
        if v is None:
            return None
        exp, val = v
        if exp and exp < time.time():
            self._d.pop(key, None)
            return None
        return val

    def set(self, key, val, ttl=3600):
        self._d[key] = (time.time() + ttl if ttl else 0, val)


class _Redis:
    kind = "redis"

    def __init__(self, url):
        import redis  # optional dependency
        self.r = redis.Redis.from_url(url, socket_timeout=2)
        self.r.ping()

    def get(self, key):
        raw = self.r.get(key)
        return None if raw is None else json.loads(raw)

    def set(self, key, val, ttl=3600):
        self.r.set(key, json.dumps(val), ex=ttl or None)


class Cache:
    def __init__(self):
        url = os.environ.get("REDIS_URL")
        self.backend = _Memory()
        if url:
            try:
                self.backend = _Redis(url)
            except Exception as e:  # fall back quietly; /api/health reports which one is live
                print(f"[cache] Redis unavailable ({e}); using in-memory cache")

    @property
    def kind(self):
        return self.backend.kind

    def get_or_set(self, key, fn, ttl=3600):
        v = self.backend.get(key)
        if v is None:
            v = fn()
            self.backend.set(key, v, ttl)
        return v


cache = Cache()
