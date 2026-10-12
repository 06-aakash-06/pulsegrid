"""Durable owner-only revision; source mutations and revision roll back together."""
from alembic import op
revision='0005_phase4_catalog_revision'
down_revision='0004_phase3_workflow'
branch_labels=depends_on=None

def upgrade():
    op.execute('CREATE TABLE catalog_revision(singleton boolean PRIMARY KEY CHECK(singleton), revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991));\n INSERT INTO catalog_revision VALUES(true,1);\n REVOKE ALL ON catalog_revision FROM pharmacy_app;\n GRANT SELECT ON catalog_revision TO pharmacy_app;\n CREATE FUNCTION pharmacy_bump_phase4_revision() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$ BEGIN\n UPDATE catalog_revision SET revision=revision+1 WHERE singleton; RETURN NULL; END $$;\n REVOKE ALL ON FUNCTION pharmacy_bump_phase4_revision() FROM PUBLIC;\nCREATE TRIGGER phase4_revision_medicines AFTER INSERT OR UPDATE OR DELETE ON medicines FOR EACH STATEMENT EXECUTE FUNCTION pharmacy_bump_phase4_revision();')

def downgrade():
    raise RuntimeError('Forward-only durable revision; use disposable rollback transactions for verification')
