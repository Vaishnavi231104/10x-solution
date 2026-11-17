"""Database-backed result cache (concept: caching logic).

Expensive work here is an LLM call. The key is a hash of everything that
influences the answer, so identical input reuses the stored result and any change
in the input produces a new key. Entries expire after a TTL and survive restarts.
"""
import datetime
import hashlib
from typing import Callable, Optional, Tuple

from sqlalchemy.orm import Session

import models


def make_key(namespace: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


def get(db: Session, key: str) -> Optional[str]:
    row = db.get(models.LlmCache, key)
    if row is None:
        return None
    if row.expires_at <= datetime.datetime.utcnow():
        db.delete(row)
        db.commit()
        return None
    row.hits = (row.hits or 0) + 1
    db.commit()
    return row.value


def put(db: Session, key: str, value: str, ttl_seconds: int) -> None:
    expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=ttl_seconds)
    row = db.get(models.LlmCache, key)
    if row is None:
        db.add(models.LlmCache(key=key, value=value, expires_at=expires, hits=0))
    else:
        row.value, row.expires_at, row.created_at = value, expires, datetime.datetime.utcnow()
    db.commit()


def get_or_compute(
    db: Session, namespace: str, parts: Tuple[str, ...], ttl_seconds: int, compute: Callable[[], str]
) -> Tuple[str, bool]:
    """Return (value, was_cached). `compute` runs only on a miss."""
    key = make_key(namespace, *parts)
    cached = get(db, key)
    if cached is not None:
        return cached, True
    value = compute()
    put(db, key, value, ttl_seconds)
    return value, False
