"""Append manual Surge Mode events to Appointment's existing audit chain."""
from alembic import op

revision = "0012_phase6_surge_audit"
down_revision = "0011_phase4_alias_parent_guard"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE UNIQUE INDEX uq_appointment_phase6_surge_requested_operation
      ON public.audit_entries ((canonical_metadata->>'operation_id'))
      WHERE chain_id='appointment'
        AND canonical_metadata->>'action'='surge_mode_transition_requested';
    CREATE UNIQUE INDEX uq_appointment_phase6_surge_terminal_operation
      ON public.audit_entries ((canonical_metadata->>'operation_id'))
      WHERE chain_id='appointment'
        AND canonical_metadata->>'action' IN ('surge_mode_transition_applied','surge_mode_transition_noop');
    CREATE FUNCTION public.appointment_append_phase6_audit(p_entry_id bigint,p_metadata jsonb)
      RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    DECLARE head public.audit_heads%ROWTYPE; canonical jsonb; calculated text;
    BEGIN
      IF p_entry_id IS NULL OR p_entry_id<=0 OR jsonb_typeof(p_metadata) IS DISTINCT FROM 'object'
        OR octet_length(p_metadata::text)>4096
        OR p_metadata->>'action' IS NULL
        OR p_metadata->>'action' NOT IN ('surge_mode_transition_requested','surge_mode_transition_applied','surge_mode_transition_noop')
        OR p_metadata->>'result' IS DISTINCT FROM 'success'
        OR p_metadata->>'actor_user_id' IS NULL
        OR (p_metadata->>'actor_user_id') !~ '^[1-9][0-9]{0,18}$'
        OR p_metadata->>'resource_id' IS DISTINCT FROM '1'
        OR p_metadata->>'request_id' IS NULL
        OR (p_metadata->>'request_id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        OR p_metadata->>'correlation_id' IS NULL
        OR (p_metadata->>'correlation_id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        OR p_metadata->>'occurred_at' IS NULL OR (p_metadata->>'occurred_at') !~ '^[0-9TZ:.+-]+$' OR length(p_metadata->>'occurred_at')>40
        OR p_metadata->>'previous_state' IS NULL
        OR p_metadata->>'previous_state' NOT IN ('NORMAL','SURGE','RECOVERY')
        OR p_metadata->>'new_state' IS NULL
        OR p_metadata->>'new_state' NOT IN ('NORMAL','SURGE','RECOVERY')
        OR p_metadata->>'reason_code' IS NULL
        OR p_metadata->>'reason_code' NOT IN ('capacity_pressure','dependency_degraded','planned_recovery','incident_override')
        OR p_metadata->>'state_version' IS NULL
        OR (p_metadata->>'state_version') !~ '^(0|[1-9][0-9]{0,15})$'
        OR p_metadata->>'operation_id' IS NULL
        OR (p_metadata->>'operation_id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        OR jsonb_typeof(p_metadata->'override') IS DISTINCT FROM 'boolean'
        OR (p_metadata->>'reason_code'='incident_override' AND p_metadata->'override' IS DISTINCT FROM 'true'::jsonb)
        OR (p_metadata->>'reason_code'<>'incident_override' AND p_metadata->'override' IS DISTINCT FROM 'false'::jsonb)
        OR (p_metadata->>'action'='surge_mode_transition_noop' AND p_metadata->>'previous_state' IS DISTINCT FROM p_metadata->>'new_state')
        OR (p_metadata->>'action'<>'surge_mode_transition_noop' AND p_metadata->>'new_state' NOT IN ('SURGE','RECOVERY'))
        OR (p_metadata->>'action'='surge_mode_transition_requested' AND p_metadata ? 'response')
        OR (p_metadata->>'action' IN ('surge_mode_transition_applied','surge_mode_transition_noop') AND (
          jsonb_typeof(p_metadata->'response') IS DISTINCT FROM 'object'
          OR p_metadata->'response'->>'state' IS NULL
          OR p_metadata->'response'->>'state' NOT IN ('NORMAL','SURGE','RECOVERY')
          OR (p_metadata->'response'->>'version') IS NULL
          OR (p_metadata->'response'->>'version') !~ '^(0|[1-9][0-9]{0,15})$'
          OR jsonb_typeof(p_metadata->'response'->'changed_at') IS DISTINCT FROM 'string' AND jsonb_typeof(p_metadata->'response'->'changed_at') IS DISTINCT FROM 'null'
          OR jsonb_typeof(p_metadata->'response'->'expires_at') IS DISTINCT FROM 'string' AND jsonb_typeof(p_metadata->'response'->'expires_at') IS DISTINCT FROM 'null'
          OR jsonb_typeof(p_metadata->'response'->'reason_code') IS DISTINCT FROM 'string' AND jsonb_typeof(p_metadata->'response'->'reason_code') IS DISTINCT FROM 'null'
          OR p_metadata->'response'->>'state' IS DISTINCT FROM p_metadata->>'new_state'
          OR p_metadata->'response'->>'version' IS DISTINCT FROM p_metadata->>'state_version'
          OR EXISTS (SELECT FROM jsonb_object_keys(p_metadata->'response') k WHERE k NOT IN
            ('state','version','changed_at','expires_at','reason_code'))
        ))
        OR EXISTS (SELECT FROM jsonb_object_keys(p_metadata) k WHERE k NOT IN
          ('action','result','actor_user_id','resource_id','request_id','correlation_id','occurred_at',
           'previous_state','new_state','reason_code','state_version','operation_id','override','response')) THEN
        RAISE EXCEPTION 'Invalid Phase 6 audit metadata' USING ERRCODE='22023';
      END IF;
      INSERT INTO public.audit_heads VALUES ('appointment',0,repeat('0',64)) ON CONFLICT DO NOTHING;
      SELECT * INTO head FROM public.audit_heads WHERE chain_id='appointment' FOR UPDATE;
      canonical:=p_metadata || jsonb_build_object('chain_id','appointment','sequence',head.last_sequence+1,'entry_id',p_entry_id::text);
      calculated:=encode(public.digest(convert_to(head.last_hash || canonical::text,'UTF8'),'sha256'),'hex');
      INSERT INTO public.audit_entries(chain_id,sequence,entry_id,prev_hash,entry_hash,canonical_metadata)
        VALUES ('appointment',head.last_sequence+1,p_entry_id,head.last_hash,calculated,canonical);
      UPDATE public.audit_heads SET last_sequence=head.last_sequence+1,last_hash=calculated WHERE chain_id='appointment';
    END $$;
    REVOKE ALL ON FUNCTION public.appointment_append_phase6_audit(bigint,jsonb) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION public.appointment_append_phase6_audit(bigint,jsonb) TO appointment_app;
    """)


def downgrade():
    raise RuntimeError("Phase 6 audit is forward-only; preserve its audit history")
