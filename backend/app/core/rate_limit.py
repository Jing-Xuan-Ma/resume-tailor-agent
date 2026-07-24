"""Small daily rate limiter with Redis when available and in-memory fallback."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from app.config import settings


class RateLimiter:
    def __init__(self) -> None:
        self._redis = None
        self._memory: dict[str, tuple[int, datetime]] = {}

    def _get_redis(self):
        if self._redis is False:
            return None
        if self._redis is None:
            try:
                import redis

                client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.2, socket_timeout=0.2)
                client.ping()
                self._redis = client
            except Exception:
                self._redis = False
                return None
        return self._redis

    def check(self, user_id: str, bucket: str, limit: int) -> None:
        now = datetime.now(UTC)
        today = now.strftime("%Y%m%d")
        key = f"rate:{bucket}:{user_id}:{today}"
        redis_client = self._get_redis()
        if redis_client:
            count = int(redis_client.incr(key))
            if count == 1:
                redis_client.expire(key, 60 * 60 * 30)
            if count > limit:
                raise HTTPException(status_code=429, detail=f"Daily {bucket} limit exceeded.")
            return

        count, expires = self._memory.get(key, (0, now + timedelta(hours=30)))
        if now > expires:
            count = 0
            expires = now + timedelta(hours=30)
        count += 1
        self._memory[key] = (count, expires)
        if count > limit:
            raise HTTPException(status_code=429, detail=f"Daily {bucket} limit exceeded.")


rate_limiter = RateLimiter()
