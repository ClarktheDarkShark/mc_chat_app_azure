"""Add session_id back to UploadedFile

Revision ID: b289749c2161
Revises: 3a8e254fec9f
Create Date: 2025-01-11 12:51:50.718390

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b289749c2161'
down_revision = '3a8e254fec9f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('uploaded_file', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_id', sa.String(length=36), nullable=False))
        batch_op.create_index(batch_op.f('ix_uploaded_file_session_id'), ['session_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('uploaded_file', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_uploaded_file_session_id'))
        batch_op.drop_column('session_id')

    # ### end Alembic commands ###
