"""add location and address type to provider profiles

Revision ID: b45a391322f2
Revises: cbc375651aa2
Create Date: 2026-09-24 21:13:55.264929

"""
from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b45a391322f2'
down_revision: Union[str, Sequence[str], None] = 'cbc375651aa2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotent: the postgis docker image only enables the extension in
    # its default database, so a fresh DB (or a CI/prod one) may not have it.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    # add_column (unlike create_table) doesn't auto-create ENUM types.
    postgresql.ENUM('shop', 'home', name='addresstype').create(op.get_bind(), checkfirst=True)
    # Both columns nullable: existing providers have no location yet.
    op.add_column('provider_profiles', sa.Column('location', geoalchemy2.types.Geography(geometry_type='POINT', srid=4326, from_text='ST_GeogFromText', name='geography'), nullable=True))
    op.add_column('provider_profiles', sa.Column('address_type', postgresql.ENUM('shop', 'home', name='addresstype', create_type=False), nullable=True))
    # No explicit create_index: GeoAlchemy2 creates the GiST spatial index
    # itself when a Geography column is added (a second one is a duplicate).


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('provider_profiles', 'address_type')
    op.drop_column('provider_profiles', 'location')
    postgresql.ENUM(name='addresstype').drop(op.get_bind(), checkfirst=True)
