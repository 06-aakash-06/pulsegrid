"""Non-executable G2 handoff for the Appointment migration owner."""


def schema_spec() -> dict:
    return {
        'tables': [{
            'name': 'queue_snapshots',
            'columns': {
                'doctor_id': 'bigint NOT NULL REFERENCES doctor_schedule_snapshots(doctor_id)',
                'local_date': 'date NOT NULL',
                'version': 'bigint NOT NULL DEFAULT 1',
                'created_at': 'timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP',
                'updated_at': 'timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP',
            },
            'primary_key': '(doctor_id, local_date)',
        }],
        'columns': [
            {'table': 'queue_entries', 'name': 'position', 'definition': 'integer NULL',
             'meaning': '1-based waiting rank; NULL for all nonwaiting states'},
        ],
        'indexes': [
            {'name': 'ix_queue_entries_one_consultation', 'existing': True,
             'sql': 'UNIQUE (doctor_id) WHERE state = \'in_consultation\''},
            {'name': 'ix_queue_entries_waiting_fifo', 'table': 'queue_entries',
             'sql': '(doctor_id, local_date, token_number, id) WHERE state = \'waiting\''},
            {'name': 'uq_queue_entries_appointment_id', 'existing': True,
             'sql': 'UNIQUE (appointment_id)'},
            {'name': 'uq_queue_entries_doctor_day_token', 'existing': True,
             'sql': 'UNIQUE (doctor_id, local_date, token_number)'},
        ],
        'constraints': [
            {'name': 'ck_queue_snapshots_safe_version', 'table': 'queue_snapshots',
             'sql': 'CHECK (version BETWEEN 1 AND 9007199254740991)'},
            {'name': 'ck_queue_entries_safe_token', 'table': 'queue_entries',
             'sql': 'CHECK (token_number BETWEEN 1 AND 9007199254740991)'},
            {'name': 'ck_queue_entries_safe_version', 'table': 'queue_entries',
             'sql': 'CHECK (version BETWEEN 1 AND 9007199254740991)'},
            {'name': 'ck_queue_entries_position', 'table': 'queue_entries',
             'sql': "CHECK ((state = 'waiting' AND position > 0) OR "
                    "(state <> 'waiting' AND position IS NULL))"},
            {'name': 'fk_queue_snapshots_doctor', 'table': 'queue_snapshots',
             'sql': 'FOREIGN KEY (doctor_id) REFERENCES doctor_schedule_snapshots(doctor_id)'},
        ],
        'preflight': [
            'Reject duplicate appointment or doctor/day/token rows and multiple active consultations per doctor.',
            'Reject token/version outside safe integer range and unknown queue state.',
            'Existing dormant queue rows require explicit review before rank backfill; do not fabricate a workflow.',
            'G2 extends lock_context to lock/create queue_snapshots under doctor parent before queue entries, '
            'and lock all waiting/active rows and affected workflows in canonical order.',
            'G2 check-in calls allocate_on_checkin only with a complete doctor/day/entry lock plan; '
            'G2 cancellation and no-show invoke terminal queue transition in the same command.',
            'G2 cancellation invokes cancel_for_booking_change after complete queue lock discovery, '
            'before the booking update; invoke check-in link revocation and journey change in that transaction.',
        ],
        'runtime_grants': [
            'GRANT SELECT, INSERT, UPDATE ON queue_snapshots TO appointment_app',
            'GRANT SELECT, UPDATE ON queue_entries TO appointment_app',
        ],
        'revision': '0007_phase3_queue after 0006_phase3_checkin; Agent 1 owns migration and shared metadata',
    }
