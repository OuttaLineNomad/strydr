from datetime import UTC, datetime


def utcnow() -> datetime:
    """Naive UTC; every DateTime column in the store holds naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)
