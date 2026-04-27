"""add_nfc_inventory_fields_idempotently

Revision ID: b6d4e8f0c2a1
Revises: a1b2c3d4e5f6
Create Date: 2026-04-27

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b6d4e8f0c2a1"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE employees ADD COLUMN IF NOT EXISTS contract_type VARCHAR(20) NOT NULL DEFAULT 'INTERNAL'"
    )
    op.execute(
        "ALTER TABLE employees ADD COLUMN IF NOT EXISTS external_company_name VARCHAR(255)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employees_contract_type ON employees (contract_type)"
    )

    op.execute(
        "ALTER TABLE nfc_cards ADD COLUMN IF NOT EXISTS label VARCHAR(120)"
    )
    op.execute(
        "ALTER TABLE nfc_cards ADD COLUMN IF NOT EXISTS card_type VARCHAR(20) NOT NULL DEFAULT 'PERMANENT'"
    )
    op.execute(
        "ALTER TABLE nfc_cards ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'ASSIGNED'"
    )
    op.execute("UPDATE nfc_cards SET card_type = 'PERMANENT' WHERE card_type IS NULL")
    op.execute("UPDATE nfc_cards SET status = 'ASSIGNED' WHERE status IS NULL")
    op.execute("ALTER TABLE nfc_cards ALTER COLUMN employee_id DROP NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_nfc_cards_label ON nfc_cards (label)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_nfc_cards_card_type ON nfc_cards (card_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_nfc_cards_status ON nfc_cards (status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_nfc_cards_status")
    op.execute("DROP INDEX IF EXISTS ix_nfc_cards_card_type")
    op.execute("DROP INDEX IF EXISTS ix_nfc_cards_label")
    op.execute("ALTER TABLE nfc_cards DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE nfc_cards DROP COLUMN IF EXISTS card_type")
    op.execute("ALTER TABLE nfc_cards DROP COLUMN IF EXISTS label")
    op.execute("DROP INDEX IF EXISTS ix_employees_contract_type")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS external_company_name")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS contract_type")
