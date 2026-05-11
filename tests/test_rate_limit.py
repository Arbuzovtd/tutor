"""Tests for RateLimitMiddleware."""
from __future__ import annotations

from collections import deque

import pytest

from app.bot.middlewares.rate_limit import RateLimitMiddleware


@pytest.fixture
def mw():
    return RateLimitMiddleware()


def test_allow_under_limit(mw):
    bucket: deque[float] = deque()
    for i in range(5):
        assert mw._allow(bucket, limit=10, window=60.0, now=float(i)) is True


def test_drop_over_limit(mw):
    bucket: deque[float] = deque()
    for i in range(10):
        assert mw._allow(bucket, limit=10, window=60.0, now=float(i)) is True
    assert mw._allow(bucket, limit=10, window=60.0, now=10.5) is False


def test_window_slides(mw):
    bucket: deque[float] = deque()
    for i in range(10):
        assert mw._allow(bucket, limit=10, window=60.0, now=float(i)) is True
    # 61 seconds later all old entries fall out
    assert mw._allow(bucket, limit=10, window=60.0, now=70.0) is True
    assert len(bucket) == 1


def test_separate_buckets_isolated(mw):
    """Different keys don't share quota."""
    a: deque[float] = deque()
    b: deque[float] = deque()
    for i in range(10):
        mw._allow(a, limit=10, window=60.0, now=float(i))
    # `a` is full but `b` still has room
    assert mw._allow(b, limit=10, window=60.0, now=11.0) is True
