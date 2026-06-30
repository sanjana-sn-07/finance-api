import json
import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SUMMARY_CACHE_TTL = int(os.getenv("SUMMARY_CACHE_TTL", "60"))

client = redis.from_url(REDIS_URL, decode_responses=True)


def get_cached(key: str) -> dict | None:
    data = client.get(key)
    return json.loads(data) if data else None


def set_cached(key: str, value: dict, ttl: int = SUMMARY_CACHE_TTL) -> None:
    client.setex(key, ttl, json.dumps(value))


def delete_cached(key: str) -> None:
    client.delete(key)
