"""Align consultation author integrity with the owned domain model."""

from alembic import op

revision = "0004_clinical_integrity"
down_revision = "0003_clinical"
branch_labels = depends_on = None


def upgrade():
    # Nullable authors on retained Phase 1 consultations remain valid.
    op.execute(
        "ALTER TABLE consultations ADD CONSTRAINT "
        "ck_consultations_author_user_id_nonnegative "
        "CHECK (author_user_id >= 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE consultations VALIDATE CONSTRAINT "
        "ck_consultations_author_user_id_nonnegative"
    )


def downgrade():
    op.execute(
        "ALTER TABLE consultations DROP CONSTRAINT "
        "ck_consultations_author_user_id_nonnegative"
    )
