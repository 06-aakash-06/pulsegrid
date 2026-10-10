"""Add profile/schedule lookup indexes, proposal conflicts, and domain audit."""

from alembic import op

revision = "0004_doctor_management"
down_revision = "0003_explicit_worker"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        "ALTER TABLE schedule_acknowledgements "
        "ADD COLUMN conflicts JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE schedule_acknowledgements ADD CONSTRAINT "
        "ck_schedule_acknowledgements_conflicts_array "
        "CHECK (jsonb_typeof(conflicts) = 'array')"
    )
    op.execute(
        "ALTER TABLE doctors ADD CONSTRAINT ck_doctors_display_name_nonempty "
        "CHECK (length(btrim(display_name)) BETWEEN 1 AND 200)"
    )
    op.execute(
        "ALTER TABLE specialties ADD CONSTRAINT ck_specialties_slug_format "
        "CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(slug) BETWEEN 1 AND 128)"
    )
    op.execute(
        "ALTER TABLE specialties ADD CONSTRAINT ck_specialties_name_nonempty "
        "CHECK (length(btrim(name)) BETWEEN 1 AND 200)"
    )
    op.execute(
        "ALTER TABLE schedule_versions ADD CONSTRAINT "
        "ck_schedule_versions_slot_minutes_range CHECK (slot_minutes BETWEEN 5 AND 120)"
    )
    op.execute(
        "CREATE INDEX ix_doctors_created_id ON doctors (created_at,id)"
    )
    op.execute(
        "CREATE INDEX ix_doctors_active_created_id ON doctors (active,created_at,id)"
    )
    op.execute(
        "CREATE INDEX ix_doctors_lower_display_name_prefix "
        "ON doctors (lower(display_name) text_pattern_ops)"
    )
    op.execute(
        "CREATE INDEX ix_specialties_created_id ON specialties (created_at,id)"
    )
    op.execute(
        "CREATE INDEX ix_schedule_versions_doctor_created_id "
        "ON schedule_versions (doctor_id,created_at,id)"
    )
    op.execute("""
    CREATE FUNCTION public.doctor_enforce_specialty_count()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog,public AS $$
    DECLARE target_id bigint; count_value integer;
    BEGIN
      FOR target_id IN
        SELECT d.id FROM public.doctors d
         WHERE d.id IN (
           CASE WHEN TG_OP <> 'INSERT' THEN OLD.doctor_id ELSE NULL END,
           CASE WHEN TG_OP <> 'DELETE' THEN NEW.doctor_id ELSE NULL END
         ) ORDER BY d.id FOR UPDATE
      LOOP
        SELECT count(*) INTO count_value
          FROM public.doctor_specialties ds WHERE ds.doctor_id=target_id;
        IF count_value < 1 OR count_value > 20 THEN
          RAISE EXCEPTION 'Doctor must have between 1 and 20 specialties'
            USING ERRCODE='23514', CONSTRAINT='ck_doctor_specialties_count';
        END IF;
      END LOOP;
      RETURN NULL;
    END; $$
    """)
    op.execute("""
    CREATE CONSTRAINT TRIGGER doctor_specialties_count_guard
      AFTER INSERT OR UPDATE OR DELETE ON doctor_specialties
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
      EXECUTE FUNCTION public.doctor_enforce_specialty_count()
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION public.doctor_enforce_specialty_count() FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.doctor_enforce_specialty_count() TO doctor_app"
    )
    op.execute("""
    CREATE FUNCTION public.doctor_append_audit(p_entry_id bigint, p_metadata jsonb)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog,public AS $$
    DECLARE head public.audit_heads%ROWTYPE; canonical jsonb; calculated text;
    BEGIN
      IF p_entry_id IS NULL OR p_entry_id <= 0
         OR jsonb_typeof(p_metadata) IS DISTINCT FROM 'object'
         OR octet_length(p_metadata::text)>4096
         OR NOT (p_metadata ?& ARRAY[
           'action','result','actor_user_id','request_id','correlation_id',
           'occurred_at','resource_type','resource_id','resource_version','details'
         ])
         OR p_metadata->>'action' IS NULL
         OR p_metadata->>'action' NOT IN (
           'doctor.profile.created','doctor.profile.updated',
           'doctor.profile.deactivated','doctor.profile.reactivated',
           'doctor.specialty.created','doctor.self.read','doctor.schedule.read',
           'doctor.schedule.proposed','doctor.schedule.reconciled',
           'doctor.identity.read','doctor.schedule_proposal.read'
         )
         OR p_metadata->>'result' IS DISTINCT FROM 'success'
         OR p_metadata->>'actor_user_id' IS NULL
         OR p_metadata->>'actor_user_id' !~ '^[1-9][0-9]{0,18}$'
         OR (length(p_metadata->>'actor_user_id')=19 AND
             p_metadata->>'actor_user_id' > '9223372036854775807')
         OR p_metadata->>'request_id' IS NULL
         OR p_metadata->>'request_id' !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
         OR p_metadata->>'correlation_id' IS NULL
         OR p_metadata->>'correlation_id' !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
         OR p_metadata->>'occurred_at' IS NULL
         OR p_metadata->>'occurred_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?Z$'
         OR p_metadata->>'resource_type' IS NULL
         OR p_metadata->>'resource_type' NOT IN ('doctor','specialty','schedule_proposal')
         OR p_metadata->>'resource_id' IS NULL
         OR p_metadata->>'resource_id' !~ '^[1-9][0-9]{0,18}$'
         OR (length(p_metadata->>'resource_id')=19 AND
             p_metadata->>'resource_id' > '9223372036854775807')
         OR p_metadata->>'resource_version' IS NULL
         OR p_metadata->>'resource_version' !~ '^[1-9][0-9]{0,15}$'
         OR (length(p_metadata->>'resource_version')=16 AND
             p_metadata->>'resource_version' > '9007199254740991')
         OR jsonb_typeof(p_metadata->'details') IS DISTINCT FROM 'object'
         OR octet_length((p_metadata->'details')::text)>512
         OR EXISTS(
           SELECT FROM jsonb_object_keys(p_metadata) k
            WHERE k NOT IN (
              'action','result','actor_user_id','request_id','correlation_id',
              'occurred_at','resource_type','resource_id','resource_version','details'
            )
         )
         OR EXISTS(
           SELECT FROM jsonb_object_keys(p_metadata->'details') k
            WHERE k NOT IN ('active','specialty_count','revision','decision','conflict_count','role')
         )
         OR ((p_metadata->'details') ? 'decision' AND
             ((p_metadata->'details'->>'decision') IS NULL OR
              (p_metadata->'details'->>'decision') NOT IN ('accepted','rejected')))
         OR ((p_metadata->'details') ? 'active' AND
             jsonb_typeof(p_metadata->'details'->'active') IS DISTINCT FROM 'boolean')
         OR ((p_metadata->'details') ? 'role' AND
             ((p_metadata->'details'->>'role') IS NULL OR
              (p_metadata->'details'->>'role') NOT IN ('doctor','receptionist','hospital_admin')))
         OR ((p_metadata->'details') ? 'specialty_count' AND
             (jsonb_typeof(p_metadata->'details'->'specialty_count') IS DISTINCT FROM 'number'
              OR (p_metadata->'details'->>'specialty_count') !~ '^([1-9]|1[0-9]|20)$'))
         OR ((p_metadata->'details') ? 'revision' AND
             (jsonb_typeof(p_metadata->'details'->'revision') IS DISTINCT FROM 'number'
              OR (p_metadata->'details'->>'revision') !~ '^[1-9][0-9]{0,15}$'
              OR (length(p_metadata->'details'->>'revision')=16 AND
                  p_metadata->'details'->>'revision' > '9007199254740991')))
         OR ((p_metadata->'details') ? 'conflict_count' AND
             (jsonb_typeof(p_metadata->'details'->'conflict_count') IS DISTINCT FROM 'number'
              OR (p_metadata->'details'->>'conflict_count') !~ '^(0|[1-9][0-9]{0,2}|1000)$'))
      THEN RAISE EXCEPTION 'Invalid Doctor audit metadata' USING ERRCODE='22023'; END IF;
      INSERT INTO public.audit_heads(chain_id,last_sequence,last_hash)
        VALUES ('domain',0,repeat('0',64)) ON CONFLICT DO NOTHING;
      SELECT * INTO head FROM public.audit_heads WHERE chain_id='domain' FOR UPDATE;
      canonical := p_metadata || jsonb_build_object(
        'chain_id','domain','sequence',head.last_sequence+1,'entry_id',p_entry_id::text
      );
      calculated := encode(public.digest(convert_to(head.last_hash || canonical::text,'UTF8'),'sha256'),'hex');
      INSERT INTO public.audit_entries(chain_id,sequence,entry_id,prev_hash,entry_hash,canonical_metadata)
        VALUES('domain',head.last_sequence+1,p_entry_id,head.last_hash,calculated,canonical);
      UPDATE public.audit_heads SET last_sequence=head.last_sequence+1,last_hash=calculated
        WHERE chain_id='domain';
    END; $$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION public.doctor_append_audit(bigint,jsonb) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.doctor_append_audit(bigint,jsonb) TO doctor_app"
    )


def downgrade():
    op.execute("DROP FUNCTION public.doctor_append_audit(bigint,jsonb)")
    op.execute("DROP TRIGGER doctor_specialties_count_guard ON doctor_specialties")
    op.execute("DROP FUNCTION public.doctor_enforce_specialty_count()")
    op.execute("DROP INDEX ix_schedule_versions_doctor_created_id")
    op.execute("DROP INDEX ix_specialties_created_id")
    op.execute("DROP INDEX ix_doctors_lower_display_name_prefix")
    op.execute("DROP INDEX ix_doctors_active_created_id")
    op.execute("DROP INDEX ix_doctors_created_id")
    op.execute(
        "ALTER TABLE schedule_versions DROP CONSTRAINT ck_schedule_versions_slot_minutes_range"
    )
    op.execute("ALTER TABLE specialties DROP CONSTRAINT ck_specialties_name_nonempty")
    op.execute("ALTER TABLE specialties DROP CONSTRAINT ck_specialties_slug_format")
    op.execute("ALTER TABLE doctors DROP CONSTRAINT ck_doctors_display_name_nonempty")
    op.execute(
        "ALTER TABLE schedule_acknowledgements DROP CONSTRAINT "
        "ck_schedule_acknowledgements_conflicts_array"
    )
    op.execute("ALTER TABLE schedule_acknowledgements DROP COLUMN conflicts")
