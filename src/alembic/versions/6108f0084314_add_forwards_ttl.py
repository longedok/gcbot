"""add forwards ttl

Revision ID: 6108f0084314
Revises: c92fec5367d1
Create Date: 2021-09-24 23:24:39.502153

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6108f0084314'
down_revision = 'c92fec5367d1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('settings', sa.Column('forwards_ttl', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    op.drop_column('settings', 'forwards_ttl')
    # ### end Alembic commands ###
