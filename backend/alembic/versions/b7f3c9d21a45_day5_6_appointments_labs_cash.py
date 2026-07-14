"""Day 5/6: appointment lifecycle cols, lab orders, cash provider

Merges the two prior heads (payments lineage `ddfb55a20f92` + conversations
`a1b2c3d4e5f6`) into a single head and adds:
  * appointments.notes / completed_at / parent_appointment_id (follow-ups)
  * lab_orders table + lab_order_status enum
  * CASH value on payment_provider (cashier collection)

Revision ID: b7f3c9d21a45
Revises: ddfb55a20f92, a1b2c3d4e5f6
Create Date: 2026-07-14 00:00:00.000000+00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7f3c9d21a45"
down_revision: str | Sequence[str] | None = ("ddfb55a20f92", "a1b2c3d4e5f6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- Cashier: add CASH to the existing payment_provider enum (in place) ---
    op.execute("ALTER TYPE payment_provider ADD VALUE IF NOT EXISTS 'CASH'")

    # --- Day 5: appointment lifecycle columns ---
    op.add_column("appointments", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "appointments",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("parent_appointment_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_appointments_parent_appointment_id"),
        "appointments",
        ["parent_appointment_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_appointments_parent_appointment_id",
        "appointments",
        "appointments",
        ["parent_appointment_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- Day 6: lab orders ---
    lab_status = postgresql.ENUM(
        "ORDERED", "COLLECTED", "RESULTED", "CANCELLED", name="lab_order_status"
    )
    lab_status.create(bind, checkfirst=True)

    op.create_table(
        "lab_orders",
        sa.Column("appointment_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("test_name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ORDERED", "COLLECTED", "RESULTED", "CANCELLED",
                name="lab_order_status", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("price_amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("resulted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lab_orders_appointment_id"), "lab_orders", ["appointment_id"], unique=False)
    op.create_index(op.f("ix_lab_orders_patient_id"), "lab_orders", ["patient_id"], unique=False)
    op.create_index(op.f("ix_lab_orders_status"), "lab_orders", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lab_orders_status"), table_name="lab_orders")
    op.drop_index(op.f("ix_lab_orders_patient_id"), table_name="lab_orders")
    op.drop_index(op.f("ix_lab_orders_appointment_id"), table_name="lab_orders")
    op.drop_table("lab_orders")
    postgresql.ENUM(name="lab_order_status").drop(op.get_bind(), checkfirst=True)

    op.drop_constraint("fk_appointments_parent_appointment_id", "appointments", type_="foreignkey")
    op.drop_index(op.f("ix_appointments_parent_appointment_id"), table_name="appointments")
    op.drop_column("appointments", "parent_appointment_id")
    op.drop_column("appointments", "completed_at")
    op.drop_column("appointments", "notes")
    # Note: Postgres can't remove the 'CASH' value from payment_provider; left in place.
