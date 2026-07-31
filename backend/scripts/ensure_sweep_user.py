"""Ensure a dev account the browser harnesses can log in with.

`vihara/scripts/sweep.mjs` needs `VIHARA_SWEEP_EMAIL` / `VIHARA_SWEEP_PASSWORD`
and aborts loudly without them — correctly, since a walk of zero surfaces that
reported success would be worse than a red one. But **which** account to use was
documented nowhere, so the sweep has been effectively unrunnable since the app
went behind a session gate, and with it every browser-level proof this increment
could have had. That is the gap this closes.

Why a script and not a line in a README: the password has to exist somewhere the
harness can read, and an account whose password is written in a document is an
account somebody eventually creates in production. This mints one on demand,
against whatever database `DATABASE_URL` points at, and refuses to run against
anything that is not obviously a development box.

    poetry run python scripts/ensure_sweep_user.py

It prints the two environment variables to feed the sweep. Re-running resets the
password rather than failing, so a forgotten password is not a dead end.

**This is a development utility.** It writes a known credential, so the refusal
below is load-bearing rather than decorative.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from src.common.config import settings  # noqa: E402
from src.common.security import get_password_hash  # noqa: E402
from src.auth.models import Company, User  # noqa: E402

# `example.com` and not `vihara.local`: `.local` is a reserved TLD and pydantic's
# EmailStr refuses it, so the account created fine and then could never log in —
# a 422 from the validator, not a 401. `example.com` is the RFC 2606 domain
# reserved for exactly this.
EMAIL = os.environ.get("VIHARA_SWEEP_EMAIL", "sweep@example.com")
COMPANY = "Vihara Sweep"


def refuse_if_not_development(url: str) -> None:
    """A known password is a liability, so this only runs where one is harmless.

    The check is on the *host*, not on an env flag: a flag is a thing somebody
    sets wrongly once, and a hostname is a fact about where the connection goes.
    """
    lowered = url.lower()
    local = any(marker in lowered for marker in ("@localhost", "@127.0.0.1", "@/", "@db:"))
    if not local:
        raise SystemExit(
            "refusing to run: DATABASE_URL does not point at a local database.\n"
            "This script writes an account with a known password and exists for "
            "the browser harnesses on a dev box. It has no business anywhere else."
        )


async def main() -> None:
    url = str(settings.DATABASE_URL)
    refuse_if_not_development(url)

    engine = create_async_engine(url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    password = os.environ.get("VIHARA_SWEEP_PASSWORD") or secrets.token_urlsafe(18)

    async with session_factory() as db:
        user = (await db.execute(select(User).where(User.email == EMAIL))).scalars().first()

        if user is None:
            company = (
                await db.execute(select(Company).where(Company.name == COMPANY))
            ).scalars().first()
            if company is None:
                # `type` is NOT NULL; "tenant" is what /auth/register creates.
                company = Company(name=COMPANY, type="tenant")
                db.add(company)
                await db.flush()

            user = User(
                email=EMAIL,
                hashed_password=get_password_hash(password),
                full_name="Vihara Sweep",
                company_id=company.id,
                role="tenant_admin",
                is_active=True,
            )
            db.add(user)
            action = "created"
        else:
            # Reset rather than refuse: a forgotten password should not be a
            # dead end for a harness, and this account has no other purpose.
            user.hashed_password = get_password_hash(password)
            user.is_active = True
            action = "reset"

        await db.commit()

    await engine.dispose()

    print(f"sweep account {action}: {EMAIL}")
    print()
    print("Run the sweep with:")
    print(f'  VIHARA_SWEEP_EMAIL={EMAIL} \\')
    print(f'  VIHARA_SWEEP_PASSWORD={password} \\')
    print("  node scripts/sweep.mjs        # from vihara/, with npm run dev up")


if __name__ == "__main__":
    asyncio.run(main())
