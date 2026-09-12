# Attendance System — End-to-End Developer Guide

Last verified against the implementation: 2026-08-04

This is the engineering contract for employee attendance in PAMAIS. It covers the mobile flow, API validation order, schedule and session resolution, security, persistence, leave integration, notifications, administration, reporting, compatibility, and regression testing.

The primary implementation is:

- API: app/api/v1/employee_attendance.py
- API schemas: app/schemas/employee_attendance.py
- Schedule exceptions: app/services/attendance_schedule_exception_service.py
- Session rollover: app/services/attendance_session_windows.py
- GPS policy: app/services/attendance_gps_freshness.py
- Request provenance: app/services/attendance_request_policy.py
- Primary phone binding: app/services/attendance_device_binding.py
- Participation policy: app/services/attendance_processing_access_service.py
- Mobile quick flow: pama_international_school/lib/screens/quick_attendance_screen.dart
- Mobile QR flow: pama_international_school/lib/screens/qr_scanner_screen.dart
- Mobile API service: pama_international_school/lib/services/employee_attendance_service.dart
- Mobile security preflight: pama_international_school/lib/services/attendance_security_service.dart

## 1. Non-negotiable design rules

Every implementation or rewrite must preserve these rules:

1. The API is authoritative. Mobile checks improve speed and messages, but never grant permission.
2. Use Asia/Phnom_Penh server time for attendance date, active windows, late status, early leave, and reporting boundaries.
3. A schedule session is 1-based externally: Session 1, Session 2, and so on.
4. One attendance_records row represents one session attempt for one employee and date.
5. Never require an employee to complete an expired earlier session before using a currently open later session, unless same-day makeup mode is enabled.
6. Never skip an earlier checkout while its checkout window is still actionable.
7. Never roll a stale request backward to an earlier session. A stale target may only move forward.
8. A missed check-in window and an open checkout window are different concepts. Late checkout minutes must not make a completely missed earlier session eligible for check-in.
9. Security checks are repeated by the API even when the phone already performed them.
10. Failed validation must not insert or update an attendance row.
11. Duplicate, concurrent, and lost-response requests must not accidentally turn one check-in into an immediate checkout.
12. Approved leave is joined at read/validation time. Do not create synthetic attendance rows for leave.
13. Store schedule and policy snapshots on attendance rows so historical reports do not change when settings change later.
14. Attendance processing exclusions apply consistently to mutation, reports, ranking, and reminders.
15. Raw device installation identifiers must never be stored; store only their one-way hash.

## 2. High-level architecture

~~~mermaid
flowchart TD
    A["Employee opens Quick Attendance or scans QR"] --> B["Client participation and primary-phone preflight"]
    B --> C["Acquire fresh precise GPS and optional daily progress"]
    C --> D["Client infers action/session for UX"]
    D --> E["Refresh GPS if prompts took time"]
    E --> F["Client device-security preflight"]
    F --> G["POST /check-in-out"]
    G --> H["API auth, participation, device, rate, GPS, branch, schedule checks"]
    H --> I["Lock employee and reconstruct today's session state"]
    I --> J["Resolve auto/explicit action with forward-only rollover"]
    J --> K["Leave and action-specific validation"]
    K --> L["Insert check-in or update checkout atomically"]
    L --> M["Commit, clear caches, notify, refresh daily progress"]
~~~

The mobile application has three attendance surfaces:

- Quick Attendance: personal attendance using live GPS. Sends qr_type=t_attendance, qr_id=1, and no branch_id. The API infers the nearest authorized branch.
- QR Scanner: scans a branch QR, standard attendance QR, or privileged administrator QR.
- Employee Attendance screen: explicit session controls. The same mutation API remains authoritative.

## 3. Core terminology and state model

For session i:

- Pending: no check-in and no checkout.
- Open: check-in exists and checkout is missing.
- Complete: both check-in and checkout exist.
- On leave: approved leave covers the session. This is a read-time state; it does not create an attendance row.
- Expired open: check-in exists, checkout is missing, and the normal checkout deadline passed.
- Missed: the check-in window passed with no check-in.

State transitions:

| Current state | Allowed transition | Result |
|---|---|---|
| Pending and check-in window open | check_in | Open |
| Pending and too early | none | Show next opening time |
| Pending and window expired | none for that session | Leave missed; evaluate later session |
| Open before minimum checkout time | none | Show remaining wait |
| Open and checkout actionable | check_out | Complete |
| Open and checkout expired, makeup off | none for old session | Leave incomplete; evaluate later session |
| Complete | none | Evaluate later session or finish day |
| On leave | none | Evaluate uncovered sessions only |

## 4. Data model

### 4.1 attendance_records

Important fields:

- user_id and attendance_date identify the employee day.
- session_index is the 1-based session number.
- check_in_time and check_out_time hold school-local event timestamps.
- check_in_latitude/longitude and check_out_latitude/longitude retain event evidence.
- check_in_branch_id and check_out_branch_id retain the validated attendance branch.
- is_mock_location and device_info retain diagnostics.
- schedule_id, scheduled_start, and scheduled_end snapshot the effective schedule.
- snapshot_late_grace_minutes and snapshot_allow_early_leave_mins preserve historical policy.
- status is normally present, late, or early_leave.
- work_hours is calculated at checkout.
- late_reason and leave_early_reason store supplied or automatic reasons.
- earned_percentage stores event credit.

Do not infer the historical schedule only from the current schedule. Prefer row snapshots whenever present.

### 4.2 Configuration and supporting tables

| Table | Purpose |
|---|---|
| attendance_schedules | Recurring weekly schedules scoped globally, by branch, department, or user |
| attendance_user_assignments | Date-effective direct user schedule assignment |
| attendance_schedule_exceptions | Date/range/monthly day-off or replacement sessions |
| attendance_schedule_exception_enrollments | Immutable employee opt-in schedule choice for a date |
| attendance_system_settings | Global security, timing, scoring-adjacent, and reminder policy |
| attendance_processing_rules | Department/user participation switches |
| attendance__allowed_branches | Additional branches where an employee may attend |
| work_locations | Active geofences, radius, and optional branch |
| attendance_primary_devices | One hashed primary phone binding per employee |
| attendance_primary_device_events | Device registration/change/reset audit history |
| check_in_security_events | Rate-limit and blocked security attempt audit |
| attendance_audit_logs | Administrative mutation audit, including manual replacement |
| holidays | Dates on which normal check-in is not required |

## 5. Global settings

The authoritative settings model is AttendanceSystemSettings.

| Setting | Meaning | Runtime/default behavior |
|---|---|---|
| require_location | Require coordinates and geofence validation | Secure default is true |
| block_mock_location | Require and reject the mock-location signal | Secure default is true |
| block_developer_options | Enable client compromised-device checks | Default false |
| allowed_ip_ranges | Comma-separated exact IPs or CIDRs | Empty means unrestricted |
| allow_early_clock_in_mins | Global early check-in minutes | Clamped to 0..240; legacy null normalizes to 240 |
| per_session_early_clock_in_mins | Per-session early override list | Missing index uses global value |
| allow_late_clock_out_mins | Checkout allowance after scheduled end | 0..1440 or legacy null; see compatibility note below |
| min_minutes_before_checkout | Earliest checkout relative to session start | Default 30 |
| session_transition_wait_mins | Wait after a completed checkout before a new check-in | Default 10, range 0..60 |
| allow_early_leave_mins | Minutes before end that do not count as early leave | Default 0 |
| allow_makeup_missing_sessions | Complete oldest incomplete sessions regardless of normal time rollover | Default false |
| late_grace_minutes | Minutes after start before check-in is marked late | Default 15 |
| notify_* | Push reminder toggles and minute offsets | See reminders section |

Important legacy note: different old code paths historically described a null allow_late_clock_out_mins as unlimited, while daily-progress and active-session rollover normalize it like zero. New configurations should store an explicit integer. If a long allowance is required, store that explicit number instead of relying on null.

## 6. Effective schedule resolution

Resolve the schedule for the target date, not just today.

Recurring schedule priority:

1. Active AttendanceUserAssignment covering the date.
2. Active schedule whose user_id matches the employee.
3. Active schedule whose department_id matches.
4. Active schedule whose branch_id matches the employee workplace.
5. Explicit global default schedule.
6. Newest effective global schedule if no explicit default exists.

Only schedules with is_active=1 and effective_date on or before the target date are candidates.

### 6.1 Weekly day configuration

Each weekday may contain:

~~~json
{
  "active": true,
  "mode": "working",
  "sessions": [
    {"start": "07:00", "end": "11:00"},
    {"start": "13:00", "end": "17:00"}
  ]
}
~~~

Accepted time inputs are normalized from start/start_time and end/end_time. A non-working or inactive day resolves to no sessions.

Legacy fallback behavior exists for old weekly records:

- Half day defaults to 08:00–12:00.
- Active full day without explicit sessions defaults to 08:00–12:00 and 13:00–17:00.

New code should always save explicit sessions.

### 6.2 Schedule exceptions

Exceptions override the recurring weekday for a target date.

Types:

- day_off: no attendance sessions.
- sessions_override: use the exception session list.

Recurrence:

- once
- date_range
- monthly

Automatic exception scope priority:

1. User
2. Department
3. Branch
4. Global

A nationality filter can further restrict Khmer/foreign staff. Optional self-enrollment exceptions are never auto-applied. They are shown before the first attendance event, validated and enrolled inside the same locked mutation transaction, and then become immutable for that employee/date.

An exception choice is rejected when:

- another choice is already enrolled;
- attendance already started;
- the exception is inactive, out of scope, not occurring on the date, not opt-in enabled, or has no valid sessions.

## 7. Session window formulas

Convert every schedule time to minutes after midnight using Cambodia time.

For session i:

    early_i = per_session_early[i] if present, otherwise global_early

    check_in_open_i = start_i - early_i

For Session 2 and later:

    check_in_open_i = max(check_in_open_i, previous_session_end)

This prevents a large early allowance for Session 2 from opening during Session 1.

Normative check-in window:

    check_in_open_i <= now <= end_i

Checkout actionability in normal mode:

    now <= end_i + late_checkout_allowance

Checkout cannot occur before:

    start_i + min_minutes_before_checkout

Early leave:

    check_out_time < end_i - allow_early_leave_mins

Late check-in:

    check_in_time > start_i + late_grace_minutes

### 7.1 Critical separation

Late checkout allowance applies only when check-in already exists. It must not extend the check-in window of a completely missed session.

Example:

- Session 1: 07:00–12:00
- Session 2: 13:00–17:00
- Current time: 13:14

Results:

- Session 1 pending: Session 1 is missed; check in to Session 2.
- Session 1 open and checkout deadline is 13:30: check out Session 1 first.
- Session 1 open and checkout deadline was 12:30: leave Session 1 incomplete and check in to Session 2.

## 8. Normal mode versus makeup mode

### Normal mode: allow_makeup_missing_sessions=false

- Time determines the current check-in session.
- An actionable earlier checkout wins.
- A pending expired earlier session is skipped.
- An expired earlier open checkout is skipped but remains visible as incomplete.
- A later session can create another open row after the previous row expires.

### Makeup mode: allow_makeup_missing_sessions=true

- Choose the oldest incomplete session first.
- A session with check-in but no checkout must be completed before the next.
- Normal late checkout cutoff does not prevent same-day completion.
- This mode deliberately disables the normal “skip expired Session 1” behavior.

Do not combine the two policies accidentally. The configuration choice changes the intended workflow.

## 9. Never-stuck rollover contract

This table is the required behavior for two sessions in normal mode:

| Session 1 state | Session 1 checkout actionable? | Session 2 window open? | Required action |
|---|---:|---:|---|
| Pending/missed | N/A | Yes | Check in Session 2 |
| Open | Yes | Yes | Check out Session 1 |
| Open | No | Yes | Check in Session 2; keep Session 1 incomplete |
| Complete | N/A | Yes | Check in Session 2 |
| On leave | N/A | Yes | Check in Session 2 if uncovered |
| Any | N/A | No | Show next opening or day closed |

The same algorithm must work for three or more sessions; do not hard-code Session 1 and Session 2.

## 10. Mobile flow

### 10.1 Common preparation

1. Prevent duplicate in-progress submissions.
2. Fetch participation status. A failed preflight may use a recent cache, but the API rechecks.
3. Check current phone against primary-phone status. Failure to load this preflight does not grant permission; the API rechecks.
4. Acquire GPS and daily progress concurrently.
5. Treat GPS as required and daily progress as optional.
6. Use server_time_minutes from daily progress for prompts and session selection.
7. Offer any eligible optional schedule exception before first attendance.

### 10.2 GPS acquisition

The mobile GPS policy:

- Ask for location service and permission.
- On iOS, request temporary full accuracy if Precise Location is reduced.
- Prefer a live sample.
- Cached reuse is allowed only for a very recent, accurate sample.
- Accept immediately at 50 m or better.
- Allow adaptive convergence up to 200 m.
- Refresh before submission when the sample is older than 45 seconds.
- Never submit accuracy <= 0 or > 200 m.

Client limits are intentionally tighter than the API’s 120-second server freshness window.

### 10.3 Client session inference

The client uses daily-progress for prompts:

1. In makeup mode, choose the oldest incomplete session.
2. In normal mode, find an open checkout whose deadline has not passed.
3. Otherwise find a pending session whose check-in window is open.
4. A missed session whose end passed must not become an explicit target.
5. If inference fails, submit action=auto without a session index and let the API decide.

Client inference never overrides server state.

### 10.4 Reason prompts

The client requests a reason when:

- check-in occurs after start + late_grace_minutes;
- checkout occurs before end - allow_early_leave_mins.

The API does not rely on the client prompt. When a late/early mutation arrives without a reason, it writes a safe automatic note.

### 10.5 Client security preflight

Based on server settings, mobile may check:

- location presence;
- platform mock/simulated location;
- known fake/default coordinates;
- accuracy;
- Android developer options, emulator, root files/apps, test keys, dangerous properties;
- iOS simulator, jailbreak indicators, debugger, and VPN;
- public IP against configured ranges.

If native verification is required but unavailable, fail closed. Client IP lookup may fail open because the API validates the connection IP independently.

Blocked client violations are sent best-effort to /security-events/client-report. Failure to report does not change the blocked outcome.

### 10.6 Submission and recovery

Before POST:

1. Refresh stale GPS.
2. Repeat client security preflight.
3. Add stable attendance device identity.
4. Send explicit action/session only when confidently resolved; otherwise auto.

After success:

- dismiss attendance reminder notifications;
- show primary-phone registration if this was first use;
- publish the attendance-updated app event;
- refresh/close the flow.

After failure:

- parse structured detail.code first;
- localize a safe message;
- offer guided recovery for GPS, device time, primary phone, and transition wait;
- keep raw technical text only for sanitized support reporting.

## 11. QR provenance contract

QR fields describe the route used; they never grant authority.

| qr_type | qr_id | branch_id | Meaning |
|---|---:|---:|---|
| t_attendance | 1 | null | Quick Attendance; API infers branch from GPS |
| branch | same as branch | same branch | Employee scanned a branch QR |
| r_attendance | 1 | null | Privileged administrator override |

Rules:

- Partial or mismatched context is rejected.
- r_attendance is valid only for an attendance administrator.
- A normal administrator using Quick Attendance does not bypass branch membership.
- Version 1.2.8 and later must provide explicit request context.
- Recognized official older builds retain the legacy compatibility path.
- Unknown or malformed clients fail closed.

## 12. POST /check-in-out request contract

Endpoint:

    POST /api/v1/employee-attendance/check-in-out

Modern Quick Attendance example:

~~~json
{
  "action": "check_in",
  "session_index": 2,
  "latitude": 11.5564,
  "longitude": 104.9282,
  "gps_accuracy_meters": 18.5,
  "gps_timestamp": "2026-08-04T06:14:01Z",
  "device_timestamp": "2026-08-04T06:14:04Z",
  "is_mock_location": false,
  "attendance_device_id": "opaque-app-scoped-id-at-least-32-characters",
  "attendance_device_name": "iPhone 15",
  "attendance_device_platform": "ios",
  "qr_type": "t_attendance",
  "qr_id": 1,
  "reason": null
}
~~~

Fields:

- action: auto, check_in, or check_out.
- session_index: optional 1-based target; normally included with explicit action.
- schedule_exception_id: optional first-action enrollment choice.
- latitude/longitude: required when location policy applies.
- gps_accuracy_meters and gps_timestamp: required for modern clients.
- device_timestamp: diagnostic only; never authorizes attendance.
- is_mock_location: required when mock blocking applies.
- attendance_device_*: stable primary-phone identity for modern clients.
- branch_id, qr_type, qr_id: provenance and branch context.
- reason: optional late or early-leave explanation.

Successful response:

~~~json
{
  "success": true,
  "message": "Session 2 Check-in Successful",
  "timestamp": "2026-08-04T13:14:05+07:00",
  "action": "check_in",
  "work_hours": null,
  "primary_device_registered": false,
  "primary_device_name": null
}
~~~

## 13. API validation pipeline

The order matters. Keep inexpensive and account-level blocks early; lock only when mutation is near.

### Phase A — identity and eligibility

1. Authenticate an active employee.
2. Check attendance processing access.
3. Parse modern device identity or apply recognized legacy compatibility.
4. Apply per-user mutation rate limit: 25 requests per 60 seconds.
5. Fast-check the existing primary phone.
6. Determine Cambodia attendance date.
7. Block normal holiday check-in. Allow explicit checkout, or auto when an open holiday record exists.

### Phase B — security and request provenance

8. Load settings with secure defaults.
9. Require mock-location signal when configured; reject true.
10. Validate request IP against exact/CIDR allowlist.
11. Reject impossible travel: over approximately 300 km/h, or over 5 km within 120 seconds.
12. Validate qr_type/qr_id/branch_id shape.
13. Restrict privileged QR to attendance administrators.
14. Build authorized branch set from workplace plus attendance__allowed_branches.
15. For Quick Attendance, infer nearest active authorized work location containing the GPS point.
16. Validate explicit/inferred branch membership.
17. Require coordinates when configured.
18. Require enhanced GPS evidence for modern/unknown clients.
19. Require GPS accuracy in 0..200 m.
20. If supplied, detect phone clock skew over 30 seconds using device_timestamp.
21. Require gps_timestamp age between -30 and +120 seconds relative to server UTC.
22. Validate coordinates against active work locations for the resolved branch or global locations.

### Phase C — schedule and serialized state

23. Resolve effective recurring schedule.
24. Ensure optional exception support exists.
25. Lock the employee row on MySQL, MariaDB, or PostgreSQL.
26. Validate and stage an optional exception enrollment inside the lock.
27. Resolve effective day and sessions again.
28. Reject non-working/no-session days.
29. Load all records for employee/date.
30. Load timing settings and reconstruct each session state.
31. Resolve active action/session.
32. Guard approved leave for the resolved session.
33. Run action-specific validation.
34. Recheck/register primary phone under the lock.
35. Mutate, commit, clear ranking cache, and queue notifications.

Any HTTP validation error rolls back. Unexpected failures roll back and return a sanitized server error.

## 14. Device and version compatibility

### Enhanced GPS evidence

- Official app 1.2.7 and later: accuracy and timestamp required.
- Recognized official builds through 1.2.6: compatibility path may omit them but still undergo mock, network, branch, geofence, and anomaly checks.
- Unknown or malformed clients: full evidence required.

### Primary phone identity and request context

- Official app 1.2.8 and later: required.
- Recognized older official builds: compatibility controlled by server configuration.
- Unknown/malformed clients: fail closed.

### App 1.3.0 stale session compatibility

The API accepts explicit action/session from 1.3.0 but performs forward-only recovery:

- stale Session 1 check-in plus currently open Session 2 becomes Session 2 check-in;
- stale expired Session 1 checkout plus currently open Session 2 becomes Session 2 check-in;
- actionable Session 1 checkout is preserved and must be completed;
- a request is never moved to an earlier session.

This lets the backend unblock old apps immediately while newer clients stop sending the stale target.

## 15. Primary attendance phone

Modern mobile builds derive an opaque stable ID:

- Android: app-signing-key/user/device scoped ANDROID_ID through the native channel.
- iOS: identifierForVendor-derived identity, with controlled fallback where necessary.

Server behavior:

1. Normalize ID, platform, and display name.
2. Hash the raw ID with SHA-256.
3. Store only the hash.
4. First successful attendance mutation auto-registers the phone atomically.
5. A different phone receives attendance_primary_device_mismatch.
6. Employee phone change is subject to a 30-day server cooldown.
7. A verified previous identity may migrate to the stable identity.
8. Authorized admin reset removes the binding; the next successful mutation registers again.
9. Device registration, migration, change, and reset are audited.

The API performs a fast primary check before expensive work and repeats it under the employee lock before mutation.

## 16. Reconstructing today’s session state

Never use row count alone.

For each attendance row:

1. Prefer a valid stored session_index.
2. For a legacy row without an index, map check-in time to a session window.
3. If no check-in mapping is possible, use checkout time with the legacy late buffer.
4. Fallback-map unmatched legacy rows sequentially to incomplete sessions.
5. Preserve separate open_record references for session-specific checkout.

In normal mode, records map primarily by stored index/time. In makeup mode, completion order and explicit stored index determine the oldest incomplete workflow.

Daily progress and mutation must use equivalent mapping rules. If one changes, update and test the other.

## 17. Resolving action and target

### 17.1 Duplicate auto replay

If action=auto arrives within 90 seconds of a newly open check-in, return the existing check-in success instead of converting the retry into checkout. This covers:

- lost HTTP success response;
- double tap;
- duplicate QR camera event.

Explicit checkout is never swallowed by this replay guard.

### 17.2 Auto action

1. Find the earliest open record whose checkout is still actionable.
2. If found, action=check_out for that session.
3. Otherwise, in makeup mode choose oldest incomplete session.
4. Otherwise choose the current check-in session from server time.
5. If no session is open, return the next opening or day-closed message.

### 17.3 Explicit check-in

1. If any earlier open checkout is actionable, reject new check-in and require checkout.
2. Validate requested session exists.
3. In makeup mode, requested session must equal oldest incomplete.
4. In normal mode, validate the requested check-in window.
5. If requested earlier session is stale and a later session is open, roll forward.
6. Never roll backward.

### 17.4 Explicit checkout

1. Validate requested session exists and has an open record.
2. Validate the open record is still actionable.
3. If the old checkout expired and a later session is now open, roll forward to later check-in.
4. Otherwise reject because no actionable check-in record is open.

## 18. Check-in mutation

Before insert:

- active session must not already be complete;
- active session must not already have a check-in;
- approved leave must not cover the session;
- transition wait after the most recent completed checkout must have elapsed.

Transition wait returns structured code=session_transition_wait with:

- wait_minutes
- remaining_seconds
- available_at
- previous_session
- next_session
- Retry-After header

Status:

    late if now > scheduled start + late grace
    otherwise present

If late and no reason is supplied, the API stores an automatic note.

Credit:

    base_event_credit = 100 / (number_of_sessions * 2)
    check_in_credit = max(0, base_event_credit - 5 if late else base_event_credit)

Insert:

- event time and GPS;
- resolved branch;
- session/schedule snapshots;
- status, reason, and credit;
- primary-phone registration in the same transaction when needed.

After commit:

- clear ranking cache;
- observe successful check-in IP patterns;
- queue Telegram notification.

## 19. Checkout mutation

Before update:

- resolved session must have open_record;
- now must be at or after scheduled session start;
- now must be at or after start + min_minutes_before_checkout;
- if a finite late cutoff applies and makeup is off, now must not exceed it.

Status:

    early_leave if now < scheduled end - early leave allowance
    otherwise keep the existing check-in status

Thus an early checkout changes a previously late/present status to early_leave.

If early and no reason is supplied, store an automatic note.

Credit:

    base_event_credit = 100 / (number_of_sessions * 2)
    checkout_credit = max(0, base_event_credit - 5 if early else base_event_credit)

Update:

- checkout time/GPS/branch;
- work_hours from check-in to checkout;
- leave_early_reason;
- missing snapshot fields via COALESCE;
- status and cumulative earned_percentage.

After commit, queue Telegram and return rounded session work hours.

## 20. Leave, holidays, and non-working days

### Approved leave

Approved leave is read from leave_request_days and merged by employee/date.

- Full-day leave covers all sessions.
- Session leave covers only listed 1-based indexes.
- Multiple approved requests merge, with fraction capped at 1.
- Covered sessions are not actionable.
- Reminders skip covered sessions.
- Reports exclude approved leave from absence.
- Canceling leave requires no attendance-row cleanup because no synthetic row exists.

### Holidays

- Normal check-in is blocked.
- Existing open checkout may still be completed.
- Attendance reminders are skipped.
- Manual attendance cannot be recorded on a holiday.
- Reports exclude holidays from expected workdays.

### Non-working/no-session days

Mutation and manual attendance are blocked. Reports do not count the date as an expected day.

## 21. Daily progress contract

Endpoint:

    GET /api/v1/employee-attendance/user/daily-progress

Important response fields:

- date and day_of_week
- server_time_minutes and server_time_iso
- expected_sessions
- session_progress/check_events
- today_records
- completed_check_ins and completed_check_outs
- expected_check_ins and expected_check_outs
- progress_percentage and is_complete
- late_grace_minutes
- system_settings
- effective schedule_exception
- schedule_exception_selection
- approved leave summary

Each session_progress entry contains:

- session_index
- start_time and end_time
- check_in_completed and check_in_time
- check_out_completed and check_out_time
- on_leave
- status: pending, partial, completed, or on_leave

Daily progress is a UX snapshot. The mutation endpoint reloads everything under server time and lock.

## 22. Security auditing and support reports

### Server security events

Blocked/anomalous attempts are stored with:

- user
- client IP
- event type/severity
- safe message
- JSON detail
- user agent

Repeated equivalent events are cooldown-deduplicated. Selected severe events can trigger Telegram security alerts.

The IP source trusts X-Forwarded-For only when the direct peer belongs to a configured trusted proxy range.

Security event deletion is restricted to active App Super Admins and creates an admin audit record.

### Client security reports

The client may report only allow-listed event types. The API chooses severity and message to prevent arbitrary audit injection.

### Employee support report

Endpoint:

    POST /api/v1/employee-attendance/support-report

Rules:

- employee explicitly taps Report Problem;
- issue code and surface are allow-listed;
- technical text is truncated and sanitized;
- rate limit is 3 per minute, separate from mutation rate limit;
- no GPS coordinates, authentication data, or arbitrary Telegram markup is accepted;
- destination uses attendance Telegram routing.

## 23. Notifications

### Push reminders

The reminder worker runs every minute in Asia/Phnom_Penh.

For each active, attendance-enabled employee and uncovered working session:

- before_in: if not checked in;
- after_in: if still not checked in;
- before_out: if checked in but not out;
- after_out: if checked in but not out.

It skips:

- holidays;
- non-working/no-session days;
- attendance-disabled employees;
- leave-covered sessions;
- already satisfied actions.

Dedup key:

    employee + session + reminder type + offset + date

Notifications contain explicit check_in/check_out actions and session_index. New reminders replace old tray reminders, and a successful attendance action dismisses remaining reminders.

### Telegram attendance notifications

After a successful commit, Telegram sends in the background when enabled:

- employee and action;
- event time/status;
- late or early duration;
- branch/location;
- coordinates and note where configured.

Destination may use branch-specific routing with global fallback. Notification failure never rolls back attendance.

## 24. Administrative workflows

Attendance administrators are role 1 users or active delegated App Admins. Teacher role 2 is not an attendance-admin shortcut.

Admin capabilities include:

- work location CRUD;
- schedule CRUD and global default;
- schedule exception CRUD/preview;
- user and bulk schedule assignment;
- allowed branch management;
- processing-access rules;
- global settings;
- attendance/security reports;
- Telegram settings;
- manual attendance replacement.

Primary-phone reset requires separate super-admin or delegated reset permission.

### Manual attendance replacement

Endpoint:

    POST /api/v1/employee-attendance/admin/manual-attendance/bulk

This intentionally bypasses employee GPS and real-time windows, but still validates:

- attendance-admin authority;
- employee active and attendance-enabled;
- branch exists and is assigned/allowed;
- valid non-future date;
- not a holiday;
- active schedule with sessions;
- unique valid session indexes;
- no checkout without check-in;
- timestamps belong to attendance date;
- matching timezone format and checkout after check-in.

After all validation:

1. Lock employee.
2. Count and delete existing rows for that employee/date.
3. Insert validated replacement rows with snapshots and computed status/work hours.
4. Write AttendanceAuditLog describing old/new counts and sessions.
5. Commit atomically.

Never delete existing rows before all replacement validation passes.

## 25. Reporting and attendance math

Report calculations must:

- use Cambodia date boundaries;
- ignore dates before employment start;
- ignore future dates for reached attendance totals;
- exclude holidays;
- count only effective working days after schedule exceptions;
- apply approved leave fractions;
- use session event counts capped at two events per session;
- prefer stored schedule/policy snapshots for late and early calculations;
- keep upcoming approved leave separate from leave already reached where the API exposes both.

Expected event count for a day:

    number_of_effective_sessions * 2

Covered leave sessions do not become absence. Reports must not treat a synthetic leave row as presence.

## 26. Concurrency and transaction safety

Required protections:

- Employee row lock serializes schedule enrollment, first phone registration, session state, and mutation.
- First check-in and optional exception enrollment commit together.
- First phone registration and attendance mutation commit together.
- Explicit session index prevents a slow request from mutating the wrong session.
- Forward-only stale recovery handles a window transition safely.
- 90-second auto replay prevents lost-response double mutation.
- Every HTTP and unexpected error rolls back.
- Telegram/push side effects occur after commit or outside critical mutation.

Do not replace the row lock with only a client mutex. Multiple devices/workers can race.

## 27. Error contract

Prefer structured errors:

~~~json
{
  "detail": {
    "code": "stable_machine_code",
    "message": "Safe user-facing message",
    "additional_field": "optional recovery metadata"
  }
}
~~~

Important codes:

- attendance_processing_disabled
- attendance_device_identity_required
- attendance_primary_device_mismatch
- attendance_device_change_locked
- attendance_request_context_required
- invalid_attendance_request_context
- invalid_branch_qr_context
- invalid_quick_attendance_context
- attendance_branch_not_assigned
- device_time_incorrect
- stale_gps
- session_transition_wait
- no_more_actions

Security/support report categories include:

- mock_location
- poor_gps_accuracy
- missing_gps_evidence
- location_required
- outside_workplace
- unauthorized_branch
- unauthorized_network
- location_anomaly
- device_security
- developer_options
- compromised_device
- debugger_attached
- vpn_active
- schedule
- server_time
- server_error
- unknown

The mobile app must mask technical exceptions and never display SQL, stack traces, raw HTML, or secrets.

## 28. Endpoint map

Base path:

    /api/v1/employee-attendance

Employee/runtime:

- GET /processing-access/me
- GET /me/schedule
- GET /user/schedule
- GET /user/daily-progress
- GET /server-time
- GET /locations
- POST /primary-device/status
- POST /primary-device/change
- POST /check-in-out
- GET /today
- GET /report
- GET /user-records
- GET /user/ranking
- POST /security-events/client-report
- POST /support-report

Attendance administration:

- GET/PATCH /admin/processing-access...
- GET/POST/PUT/DELETE /admin/work-locations...
- GET/POST/PUT/DELETE /admin/schedules...
- GET/POST/PUT/DELETE /admin/schedule-exceptions...
- GET/POST/DELETE /admin/users.../schedule and assignment routes
- GET/POST /admin/users.../allowed-branches and bulk routes
- GET/PUT /admin/settings
- GET/DELETE /admin/check-in-security-events...
- GET /admin/records
- GET /admin/report/global
- GET /admin/report/trend
- GET /admin/report/user/{user_id}/detailed
- GET/POST /admin/telegram-settings
- POST /admin/telegram-settings/test
- POST /admin/manual-attendance/bulk

## 29. Reference pseudocode

~~~text
function processAttendance(request, authenticatedEmployee):
    requireAttendanceEnabled(employee)
    identity = parseOrLegacyDeviceIdentity(request, headers)
    rateLimit(employee)
    fastCheckPrimaryPhone(identity)

    today = cambodiaServerDate()
    enforceHolidayPolicy(request, today)
    settings = loadSecureSettings()
    enforceMockIpAnomalyAndRequestContext(request, settings)
    branch = inferOrValidateAuthorizedBranch(request, employee)
    enforceGpsEvidenceFreshnessAccuracyAndGeofence(request, branch)

    schedule = resolveSchedule(employee, today)
    begin transaction
    lock employee
    enrollOptionalScheduleException(request, employee, today)
    sessions = resolveEffectiveDay(schedule, employee, today)
    records = loadTodayRecords(employee)
    states = mapRecordsToSessions(records, sessions)

    action, target = resolveTarget(
        request,
        serverTime,
        states,
        sessions,
        settings
    )

    requireSessionNotCoveredByLeave(target)

    if action == check_in:
        requireNoActionableEarlierCheckout()
        requireTargetPending()
        requireTransitionWaitComplete()
        recheckOrRegisterPrimaryPhone()
        insertCheckInWithSnapshots()
    else:
        requireTargetOpenAndActionable()
        requireCheckoutUnlockTime()
        recheckOrRegisterPrimaryPhone()
        updateCheckoutWithSnapshots()

    commit
    queueNotifications()
    return success
~~~

## 30. Required regression matrix

Every attendance change should test at least:

### Session rollover

- Session 1 untouched, Session 2 open → Session 2 check-in.
- Session 1 complete, Session 2 open → Session 2 check-in.
- Session 1 open/actionable, Session 2 open → Session 1 checkout.
- Session 1 open/expired, Session 2 open → Session 2 check-in.
- Stale explicit Session 1 check-in rolls forward.
- Stale explicit expired checkout rolls forward.
- Forward recovery never moves backward.
- Makeup mode selects oldest incomplete.
- Three-session equivalent cases.

### Timing

- earliest allowed check-in boundary;
- one minute too early;
- exact session end;
- late grace boundary;
- minimum checkout boundary;
- early-leave allowance boundary;
- late checkout boundary;
- session transition wait boundary;
- no active window/next session/all closed.

### Idempotency and concurrency

- duplicate auto within 90 seconds;
- explicit checkout is not swallowed;
- simultaneous first check-ins create one valid mutation;
- simultaneous exception selection cannot diverge;
- simultaneous first-use device registration remains one binding.

### Security

- missing/true mock signal;
- unauthorized IP;
- trusted versus untrusted forwarded IP;
- missing GPS;
- accuracy <=0 and >200;
- stale/future GPS;
- incorrect phone clock;
- impossible travel;
- outside geofence;
- unauthorized branch;
- forged privileged QR;
- invalid Quick Attendance branch injection;
- wrong primary phone;
- legacy recognized versus unknown client.

### Calendar/state

- holiday check-in blocked and open checkout allowed;
- non-working day blocked;
- full-day leave;
- per-session leave;
- schedule exception day off;
- exception session override;
- opt-in exception locks with first event;
- attendance processing disabled.

### Persistence/reporting

- snapshots stored;
- late and early status/reasons;
- work-hours calculation;
- earned percentage;
- daily progress mirrors mutation mapping;
- leave excluded from absence;
- manual replacement atomic and audited.

Current focused tests include:

- tests/test_attendance_session_windows.py
- tests/test_attendance_mutation_replay.py
- tests/test_attendance_request_policy.py
- tests/test_attendance_gps_freshness.py
- tests/test_attendance_device_compatibility.py
- tests/test_attendance_primary_device_binding.py
- tests/test_attendance_session_transition.py
- mobile test/attendance_session_windows_test.dart

## 31. Rules for extending the system

When adding a feature:

1. Decide whether it is only UX or authoritative policy.
2. Put authoritative policy in an API service/helper and test it without UI.
3. Mirror only the prompt/recovery behavior on mobile.
4. Use server time and effective target-date schedule.
5. Keep session indexes 1-based at API/database boundaries.
6. Update mutation and daily-progress mapping together.
7. Preserve old app compatibility deliberately and version-gate it.
8. Add a stable error code when mobile needs special recovery.
9. Snapshot historical inputs on the record.
10. Add concurrency, stale-request, leave, and security tests.

Avoid:

- selecting “first incomplete” in normal mode without checking expiry;
- extending missed check-in with late checkout allowance;
- trusting client branch, action, time, GPS, or admin flags;
- hard-coding exactly two sessions;
- using device time as authority;
- inserting leave as attendance;
- deleting manual rows before replacement validation;
- storing raw device identity;
- letting a preflight failure bypass API validation;
- showing raw backend exceptions to employees.

## 32. Deployment order

For attendance behavior changes:

1. Deploy backward-compatible API changes first.
2. Verify old supported app versions against production-like schedules/settings.
3. Release mobile changes that stop generating legacy/stale requests.
4. Monitor security events, support reports, and Telegram attendance results.
5. Only then disable a legacy compatibility flag, after adoption is confirmed.

For the Session 1 → Session 2 rollover fix, deploying the API first immediately supports app 1.3.0. The mobile release improves local selection and messages but is not required to unblock existing users.
