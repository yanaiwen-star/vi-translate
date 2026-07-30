"""Password hashing with bcrypt (direct, no passlib).

We avoid ``passlib.context.CryptContext`` because:
  - passlib 1.7.4's bcrypt backend reads ``bcrypt.__about__.__version__`` which
    was removed in bcrypt 4.x, breaking initialization on newer installs.
  - Even with bcrypt pinned <4, passlib still triggers a wrap-bug probe that
    occasionally fails on certain bcrypt patch versions.

Using the bcrypt package directly is simpler, faster, and version-stable.
"""
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """Return a bcrypt hash for ``password`` using a fresh 12-round salt."""
    pw = password.encode("utf-8")
    # bcrypt has a 72-byte input limit; truncate defensively for safety.
    if len(pw) > 72:
        pw = pw[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time compare ``password`` against the stored bcrypt hash."""
    if not password or not password_hash:
        return False
    try:
        pw = password.encode("utf-8")
        if len(pw) > 72:
            pw = pw[:72]
        return bcrypt.checkpw(pw, password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False

