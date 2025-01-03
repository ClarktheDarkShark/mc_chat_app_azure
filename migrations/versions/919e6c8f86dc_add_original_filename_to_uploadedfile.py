"""Add original_filename to UploadedFile

Revision ID: 919e6c8f86dc
Revises: dc55a2105145
Create Date: 2024-12-31 00:06:38.559553

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '919e6c8f86dc'
down_revision = 'dc55a2105145'
branch_labels = None
depends_on = None


def upgrade():
    # Since columns already exist, skip adding them.
    # Alternatively, ensure columns are not nullable.
    with op.batch_alter_table('uploaded_file', schema=None) as batch_op:
        batch_op.alter_column('original_filename',
                               existing_type=sa.String(length=255),
                               nullable=False)
        batch_op.alter_column('file_type',
                               existing_type=sa.String(length=100),
                               nullable=False)


def downgrade():
    # Reverse the changes if needed
    with op.batch_alter_table('uploaded_file', schema=None) as batch_op:
        batch_op.drop_column('original_filename')
        batch_op.drop_column('file_type')
