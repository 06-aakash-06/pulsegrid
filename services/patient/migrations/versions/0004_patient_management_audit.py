"""Constrained append-only audit chain for Patient management operations."""

from alembic import op

revision = "0004_patient_management_audit"
down_revision = "0003_auth_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
CREATE FUNCTION public.patient_append_audit(p_entry_id bigint, p_metadata jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE head public.audit_heads%ROWTYPE; canonical jsonb; calculated text;
BEGIN
  IF p_entry_id IS NULL
     OR p_entry_id <= 0
     OR jsonb_typeof(p_metadata) IS DISTINCT FROM 'object'
     OR octet_length(p_metadata::text) > 4096
     OR p_metadata->>'action' IS NULL
     OR p_metadata->>'action' NOT IN (
       'patient.profile.read',
       'patient.profile.list',
       'patient.profile.updated',
       'patient.user.read',
       'patient.user.list',
       'patient.user.roles_changed',
       'patient.user.account_state_changed',
       'patient.patient.status_read',
       'patient.user.staff_status_read',
       'patient.user.bootstrapped'
     )
     OR p_metadata->>'result' IS NULL
     OR p_metadata->>'result' NOT IN ('success','denied')
     OR p_metadata->>'request_id' IS NULL
     OR p_metadata->>'correlation_id' IS NULL
     OR p_metadata->>'occurred_at' IS NULL
     OR jsonb_typeof(p_metadata->'request_id') IS DISTINCT FROM 'string'
     OR jsonb_typeof(p_metadata->'correlation_id') IS DISTINCT FROM 'string'
     OR jsonb_typeof(p_metadata->'occurred_at') IS DISTINCT FROM 'string'
     OR p_metadata->>'request_id' !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
     OR p_metadata->>'correlation_id' !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
     OR p_metadata->>'occurred_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?(\\+00:00|Z)$'
     OR COALESCE(p_metadata->>'actor_type','user') NOT IN ('user','local_operator')
     OR EXISTS(
       SELECT FROM jsonb_object_keys(p_metadata) k
       WHERE k NOT IN (
         'action','result','actor_type','actor_user_id','resource_user_id',
         'patient_id','request_id','correlation_id','occurred_at','content_digest'
       )
     )
     OR (
       p_metadata ? 'content_digest'
       AND (
         jsonb_typeof(p_metadata->'content_digest') IS DISTINCT FROM 'string'
         OR p_metadata->>'content_digest' !~ '^[0-9a-f]{64}$'
       )
     )
     OR (
       p_metadata ? 'actor_user_id'
       AND (
         jsonb_typeof(p_metadata->'actor_user_id') IS DISTINCT FROM 'string'
         OR p_metadata->>'actor_user_id' !~ '^[1-9][0-9]{0,18}$'
       )
     )
     OR (
       p_metadata ? 'resource_user_id'
       AND (
         jsonb_typeof(p_metadata->'resource_user_id') IS DISTINCT FROM 'string'
         OR p_metadata->>'resource_user_id' !~ '^[1-9][0-9]{0,18}$'
       )
     )
     OR (
       p_metadata ? 'patient_id'
       AND (
         jsonb_typeof(p_metadata->'patient_id') IS DISTINCT FROM 'string'
         OR p_metadata->>'patient_id' !~ '^[1-9][0-9]{0,18}$'
       )
     )
  THEN RAISE EXCEPTION 'Invalid Patient audit metadata' USING ERRCODE='22023'; END IF;

  INSERT INTO public.audit_heads(chain_id,last_sequence,last_hash)
    VALUES ('patient',0,repeat('0',64)) ON CONFLICT DO NOTHING;
  SELECT * INTO head FROM public.audit_heads WHERE chain_id='patient' FOR UPDATE;
  canonical := p_metadata || jsonb_build_object(
    'chain_id','patient','sequence',head.last_sequence+1,'entry_id',p_entry_id::text
  );
  calculated := encode(
    public.digest(convert_to(head.last_hash || canonical::text,'UTF8'),'sha256'),
    'hex'
  );
  INSERT INTO public.audit_entries(
    chain_id,sequence,entry_id,prev_hash,entry_hash,canonical_metadata
  ) VALUES(
    'patient',head.last_sequence+1,p_entry_id,head.last_hash,calculated,canonical
  );
  UPDATE public.audit_heads
    SET last_sequence=head.last_sequence+1,last_hash=calculated
    WHERE chain_id='patient';
END $$;
"""
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.patient_append_audit(bigint,jsonb) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.patient_append_audit(bigint,jsonb) TO patient_app"
    )


def downgrade():
    op.execute("DROP FUNCTION public.patient_append_audit(bigint,jsonb)")
