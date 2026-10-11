"""Non-executable G2 migration requirements. No G1 Alembic revision."""


def schema_spec():
    return {
        'revision': '0005_phase3_waitlist', 'down_revision': '0004_phase3_core',
        'tables': [{'name': 'promotion_jobs', 'purpose': 'Durable per-slot promotion and lease recovery'}],
        'columns': [
            {'table': 'promotion_jobs', 'name': name, 'type': kind, 'nullable': nullable, 'default': default}
            for name, kind, nullable, default in (
                ('slot_id', 'bigint', False, None), ('version', 'bigint', False, '1'),
                ('attempt_count', 'integer', False, '0'), ('next_attempt_at', 'timestamptz', False, 'CURRENT_TIMESTAMP'),
                ('lease_token', 'varchar(64)', True, None), ('lease_expires_at', 'timestamptz', True, None),
                ('pending', 'boolean', False, 'true'), ('updated_at', 'timestamptz', False, 'CURRENT_TIMESTAMP'))],
        'constraints': [
            {'table': 'promotion_jobs', 'name': 'pk_promotion_jobs', 'sql': 'PRIMARY KEY (slot_id)'},
            {'table': 'promotion_jobs', 'name': 'fk_promotion_jobs_slot', 'sql': 'FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE RESTRICT'},
            {'table': 'promotion_jobs', 'name': 'ck_promotion_jobs_progress', 'sql': 'CHECK (version > 0 AND attempt_count >= 0)'},
            {'table': 'promotion_jobs', 'name': 'ck_promotion_jobs_lease', 'sql': 'CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL))'},
            {'table': 'waitlist_entries', 'name': 'ck_waitlist_outcome', 'sql': "CHECK ((state = 'promoted') = (promoted_appointment_id IS NOT NULL) AND (state = 'skipped') = (skip_reason IS NOT NULL) AND (skip_reason IS NULL OR skip_reason IN ('inactive_patient','patient_overlap','slot_retired','window_closed')))"},
            {'table': 'patient_status_snapshots', 'name': 'ck_patient_status_source', 'sql': 'CHECK (source_version >= 0 AND (source_version > 0 OR NOT active))'}],
        'indexes': [
            {'table': 'waitlist_entries', 'name': 'ix_waitlist_promoted_unique', 'sql': 'CREATE UNIQUE INDEX ix_waitlist_promoted_unique ON waitlist_entries(promoted_appointment_id) WHERE promoted_appointment_id IS NOT NULL'},
            {'table': 'promotion_jobs', 'name': 'ix_promotion_jobs_due', 'sql': 'CREATE INDEX ix_promotion_jobs_due ON promotion_jobs(next_attempt_at,slot_id) WHERE pending'}],
        'preflight': ['Stop if dormant waitlist_entries or patient_status_snapshots contain unexpected data; never delete/backfill.',
                      'Verify one waiting patient/slot and all outcome/reference checks before adding constraints.',
                      'Keep active-slot unique, patient-overlap GiST and appointment_slot_copy guards unchanged.',
                      'G2 must add aggregate promotion_jobs metadata; G1 explicit core plans lock FIFO, sorted patient status scopes/rows, jobs, then queue/journey/audit.',
                      'Review cross-row promoted reference binding to the same stored patient/slot as part of G2 aggregate constraints.'],
        'runtime_grants': [{'table': name, 'privileges': ['SELECT','INSERT','UPDATE']}
                           for name in ('promotion_jobs','waitlist_entries','patient_status_snapshots')],
    }
