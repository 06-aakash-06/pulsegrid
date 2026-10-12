"""Durable owner-only revision; source mutations and revision roll back together."""
from alembic import op
revision='0005_phase4_directory_revision'
down_revision='0004_doctor_management'
branch_labels=depends_on=None

def upgrade():
    op.execute('CREATE TABLE directory_revision(singleton boolean PRIMARY KEY CHECK(singleton), revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991));\n INSERT INTO directory_revision VALUES(true,1);\n REVOKE ALL ON directory_revision FROM doctor_app;\n GRANT SELECT ON directory_revision TO doctor_app;\n CREATE FUNCTION doctor_bump_phase4_revision() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$ BEGIN\n UPDATE directory_revision SET revision=revision+1 WHERE singleton; RETURN NULL; END $$;\n REVOKE ALL ON FUNCTION doctor_bump_phase4_revision() FROM PUBLIC;\nCREATE TRIGGER phase4_revision_doctors AFTER INSERT OR UPDATE OR DELETE ON doctors FOR EACH STATEMENT EXECUTE FUNCTION doctor_bump_phase4_revision();\nCREATE TRIGGER phase4_revision_specialties AFTER INSERT OR UPDATE OR DELETE ON specialties FOR EACH STATEMENT EXECUTE FUNCTION doctor_bump_phase4_revision();\nCREATE TRIGGER phase4_revision_doctor_specialties AFTER INSERT OR UPDATE OR DELETE ON doctor_specialties FOR EACH STATEMENT EXECUTE FUNCTION doctor_bump_phase4_revision();')

def downgrade():
    raise RuntimeError('Forward-only durable revision; use disposable rollback transactions for verification')
