"""Narrow service-only eligibility audit, without user impersonation."""
from alembic import op
revision='0005_waitlist_eligibility'
down_revision='0004_patient_management_audit'
branch_labels=depends_on=None


def upgrade():
    op.execute("""
    DO $$ DECLARE definition text; BEGIN
      definition:=pg_get_functiondef('public.patient_append_audit(bigint,jsonb)'::regprocedure);
      definition:=replace(definition, '''patient.profile.read''', '''patient.waitlist.eligibility_read'',''patient.profile.read''');
      definition:=replace(definition, '(''user'',''local_operator'')', '(''user'',''local_operator'',''service:appointment'')');
      definition:=replace(definition, 'OR COALESCE(p_metadata',
        'OR (p_metadata->>''actor_type''=''service:appointment'' AND p_metadata->>''action''<>''patient.waitlist.eligibility_read'') OR COALESCE(p_metadata');
      EXECUTE definition;
    END $$;
    """)


def downgrade():
    raise RuntimeError('Forward-only owner audit policy')
