"""Match explicit RESTRICT owner metadata on additive provenance foreign keys."""
from alembic import op
revision='0009_phase4_provenance_fks'
down_revision='0008_phase4_source_parent_guard'
branch_labels=depends_on=None

def upgrade():
    for table,column,parent in (
        ('insurance_estimates','provider_id','insurance_providers'),
        ('insurance_estimates','source_run_id','crawler_runs'),
        ('insurance_source_versions','provider_id','insurance_providers'),
        ('insurance_source_versions','observed_run_id','crawler_runs'),
    ):
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT {table}_{column}_fkey')
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT {table}_{column}_fkey FOREIGN KEY({column}) REFERENCES {parent}(id) ON DELETE RESTRICT')

def downgrade():
    raise RuntimeError('Forward-only source provenance')
