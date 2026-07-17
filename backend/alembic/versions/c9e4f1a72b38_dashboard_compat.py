"""Dashboard compatibility: provider/service slugs, appointment dashboard cols,
ADMITTED status, emergencies table.

Folds the staff-dashboard features (previously served by the throwaway
`backend-stub`) into the real backend so the frontend talks to one service:
  * providers.slug / services.slug — stable identifiers the dashboards address
  * appointments.home_reading / test_details / collection_date
  * ADMITTED value on appointment_status (doctor "Admitted / procedure")
  * emergencies table + emergency_status enum (PRD §8.6)

Revision ID: c9e4f1a72b38
Revises: b7f3c9d21a45
Create Date: 2026-07-16 00:00:00.000000+00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9e4f1a72b38"
down_revision: str | Sequence[str] | None = "b7f3c9d21a45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- Stable dashboard slugs on providers & services ---
    op.add_column("providers", sa.Column("slug", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_providers_slug"), "providers", ["slug"], unique=True)
    op.add_column("services", sa.Column("slug", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_services_slug"), "services", ["slug"], unique=True)

    # --- Appointment dashboard context columns ---
    op.add_column("appointments", sa.Column("home_reading", sa.Text(), nullable=True))
    op.add_column("appointments", sa.Column("test_details", sa.Text(), nullable=True))
    op.add_column("appointments", sa.Column("collection_date", sa.Date(), nullable=True))

    # --- Doctor "Admitted / procedure" close state ---
    op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'ADMITTED'")

    # --- Emergencies (PRD §8.6) ---
    emergency_status = postgresql.ENUM("OPEN", "ACKNOWLEDGED", name="emergency_status")
    emergency_status.create(bind, checkfirst=True)

    op.create_table(
        "emergencies",
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("OPEN", "ACKNOWLEDGED", name="emergency_status", create_type=False),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_emergencies_patient_id"), "emergencies", ["patient_id"], unique=False)
    op.create_index(op.f("ix_emergencies_status"), "emergencies", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_emergencies_status"), table_name="emergencies")
    op.drop_index(op.f("ix_emergencies_patient_id"), table_name="emergencies")
    op.drop_table("emergencies")
    postgresql.ENUM(name="emergency_status").drop(op.get_bind(), checkfirst=True)

    op.drop_column("appointments", "collection_date")
    op.drop_column("appointments", "test_details")
    op.drop_column("appointments", "home_reading")

    op.drop_index(op.f("ix_services_slug"), table_name="services")
    op.drop_column("services", "slug")
    op.drop_index(op.f("ix_providers_slug"), table_name="providers")
    op.drop_column("providers", "slug")
    # Note: Postgres can't remove the 'ADMITTED' value from appointment_status; left in place.
