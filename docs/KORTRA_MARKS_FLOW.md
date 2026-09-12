# kortra_env Marks Calculation Flow (Reference)

This document describes how kortra_env calculates and stores **monthly**, **semester**, and **yearly** marks, and how they are persisted to the database. pama_api follows this same process.

---

## 1. Trigger & Cascade Order

**When:** On every marks save or clear (INSERT/UPDATE/DELETE of `marks_input`).

**Order (within a single transaction):**
1. **Monthly** → 2. **Semester** → 3. **Yearly**

- Monthly uses `marks_input` as source.
- Semester uses `marks_monthly` as source.
- Yearly uses `marks_semester` as source.

---

## 2. Monthly Flow (`monthly_flow.py`)

### 2.1 Rule Lookup

- Table: `exam_calculate_sign`
- Filter: `academic_id`, `program_id`, `grade_group_id`, `marks_system_id`, `is_active = 1`
- **Order:** `ORDER BY id DESC LIMIT 1` (no `exam_type` filter; take newest active rule)
- Output: `result_name`, `formula_expression`, `divide_by_multiplier`

### 2.2 Subject Resolution

1. If `marks_code` in `SUBJECTS_REFERENCE_EXAM_CODES` and `formula = "exam_calculate_sign_subjects"`:
   - Load from `exam_calculate_sign_subjects`
2. Fallback 1: `marks_system_subjects`
3. Fallback 2: `subjects_group` (all subjects)
4. Fallback 3: Parse numbers from `formula_expression`

- **Deduplicate** subject IDs to avoid inflated totals.

### 2.3 Fetch Input Marks

```sql
SELECT id, marks, subject_id, updated_at, created_at
FROM marks_input
WHERE student_id, academic_id, program_id, grade_group_id, marks_system_id, subject_id IN (...)
```

- **Deduplication:** Keep **latest per subject** (sort by `updated_at`, `created_at`, `id` ascending → last occurrence wins).

### 2.4 Calculation

- Per subject: apply `calculate_marks` deduction (if configured); half-pass threshold check.
- `adjusted_total_marks` = sum of adjusted marks.
- `expected_subjects` = len(subject_ids)
- `missing_subjects_count` = max(0, expected_subjects - present_subjects)
- `adjusted_divide_by_multiplier` = divide_by_multiplier - missing_subjects_count (min 1)
- `raw_average` = adjusted_total_marks / adjusted_divide_by_multiplier
- `grade_scale_id` from `grade_scale` using `get_grade_scale_id_raw` with `max_possible_score` = max scale

### 2.5 Storage

- **Table:** `marks_monthly`
- **Rounding:** `total` and `average` rounded to 2 decimal places.
- **Junction:** `marks_monthly_items`
  - **Delete** existing rows for `marks_monthly_id`
  - **Bulk insert** `(marks_monthly_id, marks_input_id)`

---

## 3. Semester Flow (`semester_flow.py`)

### 3.1 Rule Lookup

- `exam_calculate_sign` WHERE `sign_code IN ('RSEM1', 'RSEM2')` AND `is_active = 1`
- Deduplicate by `marks_system_id` (keep first per unique key)
- Resolve `marks_system_id = 0` via `marks_system.marks_code` or `marks_name`

### 3.2 Monthly Data

- Resolve formula tokens (e.g. MON1, MON2) → `marks_system_id` via `marks_system` or legacy IDs.
- Query:
  ```sql
  SELECT exam_name, average, id, marks_system_id
  FROM marks_monthly
  WHERE student_id, academic_id, program_id, grade_group_id, marks_system_id IN (...)
  ```
- **Deduplication:** If multiple rows per `marks_system_id`, keep **latest** (highest `id`, i.e. `ORDER BY id DESC`, first row per sys_id).

### 3.3 Calculation by Mark Type

| Mark Type | Logic |
|-----------|-------|
| **EN/IEP** | Per-subject average across months; semester total = sum of subject averages; semester average = total / (subjects - missing_subjects). Deduplicate `marks_input` by (subject_id, marks_system_id) before summing. |
| **OTHER**  | Sum(monthly averages) / (divide_by_multiplier - missing_months_count) |
| **KH**     | Nested formula: grouped average + standalone sum; divisor = base - missing_components (group or standalone) |

### 3.4 Storage

- **Table:** `marks_semester`
- **Rounding:** `total`, `average` to 2 decimals
- **Junction:** `marks_semester_monthlies`
  - **Delete** existing for `marks_semester_id`
  - **Bulk insert** `(marks_semester_id, marks_monthly_id)`

---

## 4. Yearly Flow (`yearly_flow.py`)

### 4.1 Rule Lookup

- `exam_calculate_sign` WHERE `sign_code = 'YEAR'` AND `is_active = 1`
- If `triggered_by_semester_ids`: filter rules by `formula_expression REGEXP (RSEM1|RSEM2)`
- Deduplicate by `marks_system_id`

### 4.2 Semester Data

- Resolve formula tokens (RSEM1, RSEM2) → `result_name` via `exam_calculate_sign`
- Query:
  ```sql
  SELECT ms.exam_name, ms.average, ms.id
  FROM marks_semester ms
  JOIN exam_calculate_sign ecs ON ecs.result_name = ms.exam_name ...
  WHERE ecs.sign_code IN (...)
  ```
- **Deduplication:** By `exam_name` (one row per semester type)

### 4.3 Calculation

- `final_total` = sum of semester averages
- `adjusted_divide_by_multiplier` = divide_by_multiplier - missing_semester_count (min 1)
- `final_average` = final_total / adjusted_divide_by_multiplier
- Scaling for EN/IEP: map to target scale

### 4.4 Storage

- **Table:** `marks_yearly`
- **Rounding:** `total`, `average` to 2 decimals
- **Junction:** `marks_yearly_semesters`
  - **Smart sync:** diff existing vs new; `DELETE` removed links, `INSERT` new ones

---

## 5. Junction Tables (No Legacy Columns)

| Junction Table           | Links                |
|--------------------------|----------------------|
| `marks_monthly_items`    | marks_monthly → marks_input |
| `marks_semester_monthlies` | marks_semester → marks_monthly |
| `marks_yearly_semesters` | marks_yearly → marks_semester |

- Legacy `marks_input_ids`, `marks_imonthly_ids`, `marks_isemester_ids` are **not** used.
- Junction tables use **delete-all-then-insert** (monthly, semester) or **differential sync** (yearly).

---

## 6. Deduplication Summary

| Layer   | Deduplication Rule                                      |
|---------|---------------------------------------------------------|
| marks_input (monthly) | Latest per (student, subject, marks_system_id) by updated_at, created_at, id |
| marks_monthly (semester) | Latest per marks_system_id by id DESC                |
| marks_semester (yearly) | Latest per exam_name by id DESC                      |
