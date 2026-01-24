"""add user blocking

Revision ID: 153bd29952c7
Revises: 7b93140dbb45
Create Date: 2026-01-22 20:31:06.045567

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "153bd29952c7"
down_revision: Union[str, Sequence[str], None] = "7b93140dbb45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
