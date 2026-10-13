# Phase 9 continuation — 14 October 2026

## Recovery baseline

Continued existing local `main` at `5eb2ec0` (approved Reception and Consultation correction). No reset, worktree, dependency installation, backend mutation, volume reset or push was performed during recovery. Initial `git diff --check` and TypeScript passed. Initial frontend tests: 135 passed, 7 failed (changed accessible action labels, appointment tabs, and duplicate healthy badges). The corrected workflow tests subsequently passed all 142 checks.

Recovered ten modified files: advanced Patient contracts/pages; Hospital billing/emergency, patient/doctor, pharmacy, records and shared UI; WorkspaceLayout; main stylesheet imports; ControlRoom. Recovered AppointmentDoctorRail, architectural-layout.css, department-scenes.css, six corrected architectural WebPs and twelve prior Reception/Consultation scaling captures. All files were inspected before edits. The earlier department additions were implementations in progress, not verified completion.

Vite was absent. Gateway port 8080 and Grafana port 3000 were already bound by Colima forwarding; no containers were started. Started one loopback Vite server at 5173. Codex browser had no tabs, but its existing session cookies authenticated the fictional Anika Shah account when the new frontend tab loaded.

The supplied ten references are available in `/Users/aakash/Downloads/inages/`: appointment, billing, consultation, medicalrecords, emergency, waiting room, controlroom, home, pharmacy and the combined appointments/reschedule/walk-in image. Their text and controls are specifications, never application backgrounds. Six recovered corrected images contain architecture only; existing pharmacy architecture is retained. No duplicate images were generated.

## Checkpoint: Appointments and Waiting Room

Appointments: preserved the three-part register, compact fictional owner doctor roster, authoritative calendar/time slots and receipt. Collapsed duplicate complete-directory search, automatically loaded valid accepted day ranges, synchronized date control with selected day, and cleared selected booking time when changing dates. Invalid or overlong custom UTC ranges do not issue availability requests. Existing frozen command review, version/idempotency behavior, cancellation/rescheduling and short-link components remain. Updated tests navigate the management tab before reviewing an appointment.

Waiting Room: physical check-in pedestal, own-patient live queue wall and truthful position indicator. Browser selection of A034 returned token 1, position 1, one waiting and zero in consultation from Appointment. Other patients are not disclosed. No waiting-minute estimate is fabricated. The pedestal opens the existing QR camera interface; manual appointment/token confirmation remains available. Friendly development appointment labels also apply to check-in selection.

Actual browser captures are in `verification/phase9-resume/`. Main Appointments and Waiting Room were exercised at 1536×1024, 1440×900, 1280×800 and 390×844; DOM page-width checks reported no horizontal overflow. Further role, secondary workflow and department QA follows below. These checks do not imply final acceptance of all seven departments.
