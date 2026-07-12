"""virtual accounts + squad provider

Revision ID: ddfb55a20f92
Revises: 6314ab255d67
Create Date: 2026-07-12 15:23:07.331934+00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ddfb55a20f92'
down_revision: str | None = '6314ab255d67'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # payment_provider already exists (created with the payments table). Add the new
    # SQUAD value and reuse the type without re-creating it.
    op.execute("ALTER TYPE payment_provider ADD VALUE IF NOT EXISTS 'SQUAD'")
    payment_provider = postgresql.ENUM(
        'PAYSTACK', 'SQUAD', name='payment_provider', create_type=False
    )

    # New enum type for virtual accounts — create it up front.
    va_status = postgresql.ENUM('ACTIVE', 'CLOSED', name='virtual_account_status')
    va_status.create(bind, checkfirst=True)

    op.create_table('virtual_accounts',
    sa.Column('booking_id', sa.UUID(), nullable=False),
    sa.Column('provider', payment_provider, nullable=False),
    sa.Column('status', postgresql.ENUM('ACTIVE', 'CLOSED', name='virtual_account_status', create_type=False), nullable=False),
    sa.Column('account_number', sa.String(length=20), nullable=False),
    sa.Column('account_name', sa.String(length=255), nullable=False),
    sa.Column('bank_name', sa.String(length=255), nullable=True),
    sa.Column('customer_code', sa.String(length=100), nullable=True),
    sa.Column('expected_amount', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_virtual_accounts_account_number'), 'virtual_accounts', ['account_number'], unique=False)
    op.create_index(op.f('ix_virtual_accounts_booking_id'), 'virtual_accounts', ['booking_id'], unique=True)
    op.create_index(op.f('ix_virtual_accounts_customer_code'), 'virtual_accounts', ['customer_code'], unique=False)
    op.create_index(op.f('ix_virtual_accounts_status'), 'virtual_accounts', ['status'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_index(op.f('ix_virtual_accounts_status'), table_name='virtual_accounts')
    op.drop_index(op.f('ix_virtual_accounts_customer_code'), table_name='virtual_accounts')
    op.drop_index(op.f('ix_virtual_accounts_booking_id'), table_name='virtual_accounts')
    op.drop_index(op.f('ix_virtual_accounts_account_number'), table_name='virtual_accounts')
    op.drop_table('virtual_accounts')
    # Drop the virtual-account enum type. Note: Postgres cannot remove the 'SQUAD'
    # value added to payment_provider, so that value is intentionally left in place.
    postgresql.ENUM(name='virtual_account_status').drop(op.get_bind(), checkfirst=True)
