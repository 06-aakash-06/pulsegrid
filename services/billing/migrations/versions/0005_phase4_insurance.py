"""Reviewed additive synthetic insurance schema; reject unproven dormant data."""
from alembic import op
revision='0005_phase4_insurance'
down_revision='0004_phase3_workflow'
branch_labels=depends_on=None

def upgrade():
    op.execute("DO $$ BEGIN\n IF EXISTS(SELECT FROM insurance_rules) OR EXISTS(SELECT FROM insurance_estimates) OR EXISTS(SELECT FROM crawler_runs) THEN\n RAISE EXCEPTION 'Dormant insurance rows require reviewed provenance backfill; no automatic guessing'; END IF;\n IF EXISTS(SELECT FROM insurance_providers WHERE synthetic_slug NOT LIKE 'phase4-synthetic-%') THEN\n RAISE EXCEPTION 'Dormant insurance providers require explicit fixture mapping review'; END IF;\n END $$;\nALTER TABLE crawler_runs ADD COLUMN pages_processed integer NOT NULL DEFAULT 0 CHECK(pages_processed>=0);\nALTER TABLE crawler_runs ADD COLUMN pages_retrieved integer NOT NULL DEFAULT 0 CHECK(pages_retrieved>=0);\nALTER TABLE crawler_runs ADD COLUMN pages_failed integer NOT NULL DEFAULT 0 CHECK(pages_failed>=0);\nALTER TABLE crawler_runs ADD COLUMN pages_invalid integer NOT NULL DEFAULT 0 CHECK(pages_invalid>=0);\nALTER TABLE crawler_runs ADD COLUMN pages_deduplicated integer NOT NULL DEFAULT 0 CHECK(pages_deduplicated>=0);\nALTER TABLE crawler_runs ADD COLUMN policies_accepted integer NOT NULL DEFAULT 0 CHECK(policies_accepted>=0);\nALTER TABLE crawler_runs ADD COLUMN policies_quarantined integer NOT NULL DEFAULT 0 CHECK(policies_quarantined>=0);\nALTER TABLE crawler_runs ADD COLUMN lease_owner varchar(128), ADD COLUMN lease_until timestamptz,\n ADD COLUMN fencing_version bigint NOT NULL DEFAULT 0 CHECK(fencing_version>=0),\n ADD COLUMN attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count BETWEEN 0 AND 3),\n ADD COLUMN next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,\n ADD CONSTRAINT ck_phase4_run_state CHECK(state IN ('pending','running','complete','partial','failed'));\nCREATE UNIQUE INDEX uq_insurance_active_run ON crawler_runs(provider_id) WHERE state IN ('pending','running');\nCREATE INDEX ix_insurance_claim_due ON crawler_runs(next_attempt_at,created_at) WHERE state IN ('pending','running');\nALTER TABLE insurance_rules ADD COLUMN policy_code varchar(64) NOT NULL,\n ADD COLUMN content_hash char(64) NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),\n ADD COLUMN effective_to timestamptz NOT NULL CHECK(effective_to>effective_from),\n ADD CONSTRAINT ck_phase4_policy_code CHECK(policy_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$');\nCREATE UNIQUE INDEX uq_insurance_source_revision ON insurance_rules(provider_id,policy_code,((rule_data->'policy'->>'revision')::bigint));\nALTER TABLE insurance_estimates ADD COLUMN invoice_version bigint NOT NULL CHECK(invoice_version BETWEEN 1 AND 9007199254740991),\n ADD COLUMN provider_id bigint NOT NULL REFERENCES insurance_providers(id),\n ADD COLUMN source_run_id bigint NOT NULL REFERENCES crawler_runs(id),\n ADD COLUMN rule_revision bigint NOT NULL CHECK(rule_revision BETWEEN 1 AND 9007199254740991),\n ADD COLUMN currency char(3) NOT NULL CHECK(currency='INR'),\n ADD COLUMN eligible_minor bigint NOT NULL CHECK(eligible_minor BETWEEN 0 AND 9007199254740991),\n ADD CONSTRAINT ck_phase4_estimate_safe CHECK(estimate_minor BETWEEN 0 AND 9007199254740991),\n ADD CONSTRAINT ck_phase4_freshness CHECK(freshness_state IN ('fresh','stale'));\nCREATE TABLE insurance_source_versions(\n provider_id bigint NOT NULL REFERENCES insurance_providers(id),source_id varchar(128) NOT NULL,source_path varchar(2048) NOT NULL,\n source_version bigint NOT NULL CHECK(source_version>0),content_hash varchar(64) NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),\n observed_run_id bigint NOT NULL REFERENCES crawler_runs(id),observed_at timestamptz NOT NULL,\n PRIMARY KEY(provider_id,source_id,source_path));\nCREATE INDEX ix_insurance_source_versions_provider_observed ON insurance_source_versions(provider_id,observed_at);\nREVOKE ALL ON insurance_providers,insurance_rules,insurance_estimates,crawler_runs,insurance_source_versions FROM billing_app;\nGRANT SELECT ON insurance_providers TO billing_app;\nGRANT SELECT,INSERT ON insurance_rules,insurance_estimates TO billing_app;\nGRANT SELECT,INSERT,UPDATE ON crawler_runs,insurance_source_versions TO billing_app;\nDO $$ DECLARE definition text; BEGIN\n definition:=pg_get_functiondef('public.billing_append_audit(bigint,jsonb)'::regprocedure);\n definition:=replace(definition, $old$'tariff.create'$old$, $new$'insurance.refresh_requested','insurance.crawl_completed','insurance.rule_accepted','insurance.source_revision_conflict','insurance.estimate_created','tariff.create'$new$);\n EXECUTE definition;\nEND $$;\n")

def downgrade():
    raise RuntimeError('Forward-only financial/provenance history')


# Separate constrained worker audit leaf: old user audit semantics remain intact.
_INSURANCE_AUDIT = """
CREATE FUNCTION public.billing_append_insurance_audit(p_entry_id bigint,p_metadata jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE head public.audit_heads%ROWTYPE; canonical jsonb; calculated text;
BEGIN
 IF p_entry_id<=0 OR jsonb_typeof(p_metadata) IS DISTINCT FROM 'object' OR octet_length(p_metadata::text)>4096
 OR p_metadata->>'action' IS NULL OR p_metadata->>'action' NOT IN ('insurance.refresh_requested','insurance.crawl_completed','insurance.rule_accepted','insurance.source_revision_conflict','insurance.estimate_created')
 OR p_metadata->>'result' IS DISTINCT FROM 'success'
 OR NOT ((p_metadata->>'actor_user_id' ~ '^[1-9][0-9]{0,18}$' AND NOT p_metadata ? 'actor_service')
    OR (p_metadata->>'actor_service'='billing' AND NOT p_metadata ? 'actor_user_id' AND p_metadata->>'action' IN ('insurance.crawl_completed','insurance.rule_accepted','insurance.source_revision_conflict')))
 OR p_metadata->>'resource_id' IS NULL OR p_metadata->>'request_id' IS NULL OR p_metadata->>'correlation_id' IS NULL OR p_metadata->>'occurred_at' IS NULL
 OR EXISTS(SELECT FROM jsonb_object_keys(p_metadata) k WHERE k NOT IN ('action','result','actor_user_id','actor_service','resource_id','request_id','correlation_id','occurred_at'))
 THEN RAISE EXCEPTION 'Invalid insurance audit metadata' USING ERRCODE='22023'; END IF;
 INSERT INTO public.audit_heads VALUES('billing',0,repeat('0',64)) ON CONFLICT DO NOTHING;
 SELECT * INTO head FROM public.audit_heads WHERE chain_id='billing' FOR UPDATE;
 canonical:=p_metadata || jsonb_build_object('chain_id','billing','sequence',head.last_sequence+1,'entry_id',p_entry_id::text);
 calculated:=encode(public.digest(convert_to(head.last_hash || canonical::text,'UTF8'),'sha256'),'hex');
 INSERT INTO public.audit_entries(chain_id,sequence,entry_id,prev_hash,entry_hash,canonical_metadata)
 VALUES('billing',head.last_sequence+1,p_entry_id,head.last_hash,calculated,canonical);
 UPDATE public.audit_heads SET last_sequence=head.last_sequence+1,last_hash=calculated WHERE chain_id='billing';
END $$;
REVOKE ALL ON FUNCTION public.billing_append_insurance_audit(bigint,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.billing_append_insurance_audit(bigint,jsonb) TO billing_app;
"""
_original_upgrade=upgrade

def upgrade():
    _original_upgrade()
    op.execute(_INSURANCE_AUDIT)
