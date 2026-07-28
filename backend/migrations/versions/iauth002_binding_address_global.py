"""A channel address belongs to at most one tenant

Revision ID: iauth002
Revises: lib002
Create Date: 2026-07-26

Owner decision, 2026-07-26: **Pragya answers on a single shared phone number**,
serving every tenant, rather than one number per tenant.

That inverts Increment-4 decision 5 ("the number is the routing
discriminator"), and the consequence lands here. When the dialled number is
the same for everyone it no longer says which company the caller reached — the
caller's *own* address does. Which only works if an address cannot mean two
tenants at once.

Enforced structurally rather than resolved at call time. The alternatives were
asking the caller "which business?" or picking their most recently active
tenant, and a wrong pick there is a cross-tenant disclosure read aloud over the
phone. Same reasoning as LEARN's B10 guarantee: make it impossible to
represent, not merely impolite to do.

**Partial on `revoked_at IS NULL`** so a revoked binding is history — somebody
who genuinely leaves one business for another must be able to register the
same phone at the new one.

The pre-existing per-company constraint stays: it answers a different question
(one address, one user, within a tenant).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'iauth002'
down_revision: Union[str, Sequence[str], None] = 'lib002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_channel_binding_address_global",
        "channel_bindings",
        ["channel_kind", "address"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_channel_binding_address_global", table_name="channel_bindings")
