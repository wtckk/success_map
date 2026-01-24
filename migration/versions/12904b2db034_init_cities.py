"""init cities

Revision ID: 12904b2db034
Revises: 38ce71380214
Create Date: 2026-01-24 05:31:16.752711

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12904b2db034'
down_revision: Union[str, Sequence[str], None] = '38ce71380214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO cities (name) VALUES
        ('Тюмень'),
        ('Москва'),
        ('Волгоград'),
        ('Сочи'),
        ('Пенза'),
        ('Тверь'),
        ('Рязань'),
        ('Санкт-Петербург'),
        ('Череповец'),
        ('Краснодар')
        ON CONFLICT (name) DO NOTHING;
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM cities WHERE name IN (
        'Тюмень',
        'Москва',
        'Волгоград',
        'Сочи',
        'Пенза',
        'Тверь',
        'Рязань',
        'Санкт-Петербург',
        'Череповец',
        'Краснодар'
        );
        """
    )