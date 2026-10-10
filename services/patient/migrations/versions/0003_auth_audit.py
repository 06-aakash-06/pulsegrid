"""Constrained append-only auth audit access for the Patient runtime role."""

from alembic import op

revision = "0003_auth_audit"
down_revision = "0002_explicit_worker"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("""
    CREATE FUNCTION public.auth_append_audit(p_entry_id bigint, p_metadata jsonb)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    DECLARE head public.audit_heads%ROWTYPE; canonical jsonb; calculated text;
    BEGIN
      IF p_entry_id <= 0 OR jsonb_typeof(p_metadata) <> 'object' OR octet_length(p_metadata::text)>4096
         OR p_metadata->>'action' IS NULL OR p_metadata->>'result' IS NULL
         OR p_metadata->>'action' NOT IN ('auth.register','auth.login','auth.refresh','auth.logout','auth.refresh_rejected','auth.profile_read','auth.authority_check')
         OR p_metadata->>'result' NOT IN ('success','denied')
         OR EXISTS(SELECT FROM jsonb_object_keys(p_metadata) k WHERE k NOT IN ('action','result','actor_user_id','request_id','correlation_id','occurred_at'))
      THEN RAISE EXCEPTION 'Invalid auth audit metadata' USING ERRCODE='22023'; END IF;
      INSERT INTO public.audit_heads(chain_id,last_sequence,last_hash) VALUES ('auth',0,repeat('0',64)) ON CONFLICT DO NOTHING;
      SELECT * INTO head FROM public.audit_heads WHERE chain_id='auth' FOR UPDATE;
      canonical := p_metadata || jsonb_build_object('chain_id','auth','sequence',head.last_sequence+1,'entry_id',p_entry_id::text);
      calculated := encode(public.digest(convert_to(head.last_hash || canonical::text,'UTF8'),'sha256'),'hex');
      INSERT INTO public.audit_entries(chain_id,sequence,entry_id,prev_hash,entry_hash,canonical_metadata)
        VALUES('auth',head.last_sequence+1,p_entry_id,head.last_hash,calculated,canonical);
      UPDATE public.audit_heads SET last_sequence=head.last_sequence+1,last_hash=calculated WHERE chain_id='auth';
    END $$;
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION public.auth_append_audit(bigint,jsonb) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.auth_append_audit(bigint,jsonb) TO patient_app"
    )


def downgrade():
    op.execute("DROP FUNCTION public.auth_append_audit(bigint,jsonb)")
