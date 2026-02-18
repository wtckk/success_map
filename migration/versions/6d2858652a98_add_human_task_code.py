"""add human task code

Revision ID: 6d2858652a98
Revises: 6014d7d351d2
Create Date: 2026-02-18 18:49:47.370372

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d2858652a98'
down_revision: Union[str, Sequence[str], None] = '6014d7d351d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("human_code", sa.String(length=16), nullable=True),
    )

    op.execute(
        """
        UPDATE public.tasks
        SET human_code =
            CASE
                WHEN source = 'Яндекс Карты' THEN 'YAN-'
                WHEN source = 'Google Maps' THEN 'GGL-'
                WHEN source = '2ГИС' THEN 'GIS-'
                ELSE 'MAP-'
            END
            ||
            upper(substr(replace(id::text, '-', ''), 1, 6))
        """
    )

    op.alter_column("tasks", "human_code", nullable=False)

    op.create_unique_constraint(
        "uq_tasks_human_code",
        "tasks",
        ["human_code"],
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_tasks_human_code", "tasks", type_="unique")
    op.drop_column("tasks", "human_code")