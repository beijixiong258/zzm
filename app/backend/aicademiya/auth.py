"""Bounded authentication throttles and compatible session/password checks."""
from collections import deque
import hashlib
import math
import secrets
import threading
import time

from fastapi import HTTPException

from .db import now, password_hash, password_matches


class RateLimiter:
    """Single-process sliding windows; keys contain only opaque hashes.

    Intended for the shipped one-worker runtime. Restart resets transient limits;
    public ingress must also impose connection/rate limits. Full capacity fails
    closed instead of evicting active buckets that an attacker could cycle.
    """
    def __init__(self, *, clock=time.monotonic, capacity=4096):
        self.clock = clock
        self.capacity = capacity
        self.secret = secrets.token_bytes(32)
        self.lock = threading.Lock()
        self.buckets = {}

    def check(self, category, identity, limit, window):
        key = (category, hashlib.blake2b(str(identity).encode(), key=self.secret, digest_size=16).digest())
        with self.lock:
            stamp = self.clock()
            # All configured windows are at most five minutes.
            for stale in [k for k, values in self.buckets.items() if not values or values[-1] <= stamp - 300]:
                del self.buckets[stale]
            values = self.buckets.get(key)
            if values is None:
                if len(self.buckets) >= self.capacity:
                    raise HTTPException(429, 'Too many requests; try again later', headers={'Retry-After': '300'})
                values = self.buckets[key] = deque()
            while values and values[0] <= stamp - window:
                values.popleft()
            if len(values) >= limit:
                retry = max(1, math.ceil(window - (stamp - values[0])))
                raise HTTPException(429, 'Too many requests; try again later', headers={'Retry-After': str(retry)})
            values.append(stamp)


class PasswordVerifier:
    def __init__(self):
        # Unknown/archived accounts still do one real scrypt verification, without
        # changing existing stored hashes or revalidating legacy password policy.
        self.dummy = password_hash(secrets.token_urlsafe(32))

    def matches(self, password, row):
        encoded = row['password_hash'] if row and row['password_hash'] else self.dummy
        matched = password_matches(password, encoded)
        return bool(row and not row['archived_at'] and matched)


def session_user(conn, token, *, demo_enabled):
    if not token or len(token) > 256 or not token.isascii():
        raise HTTPException(401, 'Sign in required')
    digest = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute('SELECT u.* FROM users u JOIN auth_sessions a ON a.user_id=u.id WHERE a.token_hash=? AND a.expires_at>?', (digest, now())).fetchone()
    if not row or row['archived_at'] or (row['is_demo'] and not demo_enabled):
        raise HTTPException(401, 'Session expired or unavailable; sign in again')
    return row
