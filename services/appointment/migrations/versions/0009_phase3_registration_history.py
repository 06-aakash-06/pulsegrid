"""Narrow append-only prerequisite history after reviewed feature schema."""
from alembic import op
revision = '0009_phase3_registration_history'
down_revision = '0008_phase3_journey'
branch_labels = depends_on = None


def upgrade():
    op.execute("""
    CREATE FUNCTION public.journey_registration_transition(jid bigint) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$ BEGIN
      IF NOT EXISTS(SELECT FROM journeys WHERE id=jid) THEN RAISE EXCEPTION 'Unknown journey'; END IF;
      INSERT INTO journey_transitions(journey_id,stage,to_state,effect_key)
      VALUES(jid,'registration','complete','registration:'||jid::text) ON CONFLICT(effect_key) DO NOTHING;
    END $$;
    REVOKE ALL ON FUNCTION public.journey_registration_transition(bigint) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION public.journey_registration_transition(bigint) TO appointment_app;
    """)


def downgrade():
    raise RuntimeError('Forward-only prerequisite history')
