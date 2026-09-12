# Marking System Overview

## Table of Contents
1. [Introduction](#introduction)
2. [System Architecture](#system-architecture)
3. [Data Flow](#data-flow)
4. [Calculation Process](#calculation-process)
5. [Database Schema](#database-schema)
6. [API Endpoints](#api-endpoints)
7. [Transaction Safety](#transaction-safety)
8. [Developer Guide](#developer-guide)

---

## Introduction

The Marking System is a comprehensive solution for managing student marks across monthly, semester, and yearly exams. It ensures data integrity, accurate calculations, and proper grade scaling.

### Key Features
- ✅ Month-based validation for mark entry
- ✅ Automatic calculation of monthly, semester, and yearly marks
- ✅ Support for Khmer, English, and IEP programs
- ✅ Decimal precision handling
- ✅ Transaction-safe operations
- ✅ Duplicate prevention

---

## System Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Flutter Mobile App                        │
│  - marking_entermark_screen.dart                             │
│  - marking_service.dart                                      │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/REST API
┌──────────────────────▼──────────────────────────────────────┐
│                   FastAPI Backend                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API Layer (marks.py)                                │  │
│  │  - /marks/exams                                       │  │
│  │  - /marks/subjects                                    │  │
│  │  - /marks/students                                    │  │
│  │  - /marks/save                                        │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                          │
│  ┌──────────────▼───────────────────────────────────────┐  │
│  │  Calculation Layer (marks_calculations.py)           │  │
│  │  - calculate_and_store_monthly_marks()                │  │
│  │  - calculate_and_store_semester_marks()               │  │
│  │  - calculate_and_store_yearly_marks()                 │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                          │
│  ┌──────────────▼───────────────────────────────────────┐  │
│  │  Models Layer (marks.py)                             │  │
│  │  - MarksSystem, MarksInput, MarksMonthly              │  │
│  │  - MarksSemester, MarksYearly                         │  │
│  │  - ExamCalculateSign, GradeScale                      │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │ SQL Queries
┌──────────────────────▼──────────────────────────────────────┐
│                    MySQL Database                            │
│  - marks_input, marks_monthly, marks_semester, marks_yearly │
│  - exam_calculate_sign, subjects_group, grade_scale         │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Mark Entry Flow

```
Teacher enters marks
        │
        ▼
Flutter App validates (0 <= mark <= full_marks)
        │
        ▼
POST /marks/save
        │
        ▼
FastAPI validates month-based deadline
        │
        ▼
Save to marks_input (DELETE old + INSERT new)
        │
        ▼
Trigger calculations:
  ├─ Monthly calculation
  ├─ Semester calculation (if monthly updated)
  └─ Yearly calculation (if semester updated)
        │
        ▼
Single COMMIT (all or nothing)
        │
        ▼
Return success to Flutter App
```

### 2. Calculation Flow

```
marks_input saved
        │
        ▼
calculate_and_store_monthly_marks()
  ├─ Get divide_by_multiplier
  ├─ Get subject rules (full_marks, calculate_marks)
  ├─ Calculate adjusted marks
  ├─ Adjust divide_by_multiplier for missing subjects
  ├─ Calculate raw_average
  └─ Store in marks_monthly
        │
        ▼
calculate_and_store_semester_marks()
  ├─ Check mark_type (kh/en/iep)
  ├─ If English/IEP: Sum all subjects
  ├─ If Khmer: Parse formula (grouped + standalone)
  ├─ Adjust divisor for missing exams
  └─ Store in marks_semester (marks_imonthly_ids)
        │
        ▼
calculate_and_store_yearly_marks()
  ├─ Get semester averages
  ├─ Adjust divide_by_multiplier
  └─ Store in marks_yearly (marks_isemester_ids)
```

---

## Calculation Process

### Monthly Calculation

**Purpose:** Calculate monthly exam results from subject marks.

**Formula:**
```
raw_average = adjusted_total_marks / adjusted_divide_by_multiplier
```

**Steps:**
1. Get `divide_by_multiplier` from `exam_calculate_sign` (exam_type='input')
2. Get total subjects count from `subjects_group`
3. Get subject rules (full_marks, calculate_marks)
4. Get student marks from `marks_input`
5. For each subject mark:
   - If `raw_mark < full_marks/2` → adjusted_mark = 0
   - Else: `adjusted_mark = raw_mark - (full_marks * calculate_marks/100)`
6. Sum all adjusted marks → `adjusted_total_marks`
7. Count subjects with marks → `student_subject_count`
8. Adjust multiplier: `adjusted_divide_by_multiplier = divide_by_multiplier - (total_subjects - student_subject_count)`
9. Calculate: `raw_average = adjusted_total_marks / adjusted_divide_by_multiplier`
10. Store in `marks_monthly` with `marks_input_ids` (comma-separated)

**Key Points:**
- Uses `exam_name` from `exam_calculate_sign.result_name`
- Stores `marks_input_ids` as comma-separated string
- Uses raw average (not percentage) for grade scale lookup

### Semester Calculation

**Purpose:** Calculate semester results from monthly averages.

**Two Methods:**

#### Method 1: English/IEP Programs
```
final_average = sum(all_adjusted_subject_marks) / subject_count
```

**Steps:**
1. Get all subjects from `marks_input` (with calculate_marks adjustments)
2. Sum all adjusted marks
3. Divide by subject count

#### Method 2: Khmer Programs
```
final_total = average_of_grouped_exams + sum_of_standalone_exams
final_average = final_total / adjusted_divisor
```

**Steps:**
1. Parse formula: `(57+58+60+56)+62`
   - Grouped: `[57, 58, 60, 56]` (inside parentheses)
   - Standalone: `[62]` (outside parentheses)
2. Get monthly averages for grouped and standalone exams
3. Calculate `average_of_grouped_exams`
4. Calculate `sum_of_standalone_exams`
5. Base divisor = number of grouped exams
6. Adjust divisor: `base_divisor - missing_grouped_exams_count`
7. Calculate: `final_average = (average_of_group + standalone_total) / adjusted_divisor`
8. Store in `marks_semester` with `marks_imonthly_ids` (comma-separated)

**Key Points:**
- Only grouped exams count for divisor
- Standalone exams are added to total but don't affect divisor
- Stores `marks_imonthly_ids` (IDs from `marks_monthly.id`)

### Yearly Calculation

**Purpose:** Calculate yearly results from semester averages.

**Formula:**
```
final_average = sum(semester_averages) / adjusted_divide_by_multiplier
```

**Steps:**
1. Check if English program (may skip if no yearly rules)
2. Get `divide_by_multiplier` from `exam_calculate_sign` (exam_type='yearly')
3. Parse formula to get semester exam IDs
4. Get semester averages by `exam_name` (not marks_system_id)
5. Sum all semester averages → `final_total`
6. Adjust multiplier: `divide_by_multiplier - missing_semester_exams_count`
7. Calculate: `final_average = final_total / adjusted_divide_by_multiplier`
8. Store in `marks_yearly` with `marks_isemester_ids` (comma-separated)

**Key Points:**
- Uses `exam_name` to match semester records
- Stores `marks_isemester_ids` (IDs from `marks_semester.id`)

---

## Database Schema

### Core Tables

#### `marks_input`
Raw marks entered by teachers.

**Columns:**
- `id` (PK)
- `student_id`
- `program_id`, `grade_id`, `grade_group_id`, `academic_id`
- `subject_id`
- `marks_system_id`
- `marks` (Numeric(10,2))
- `created_at`, `updated_at`

#### `marks_monthly`
Calculated monthly exam results.

**Columns:**
- `id` (PK)
- `exam_name` (from exam_calculate_sign.result_name)
- `student_id`
- `program_id`, `grade_id`, `grade_group_id`, `academic_id`
- `marks_system_id`
- `marks_input_ids` (Text, comma-separated)
- `total` (Numeric(10,2))
- `average` (Numeric(10,2))
- `grade_scale_id`
- `created_at`, `updated_at`

#### `marks_semester`
Calculated semester exam results.

**Columns:**
- `id` (PK)
- `exam_name`
- `student_id`
- `program_id`, `grade_id`, `grade_group_id`, `academic_id`
- `marks_system_id`
- `marks_imonthly_ids` (Text, comma-separated) ⚠️ **Note: "i" before "monthly"**
- `total` (Numeric(10,2))
- `average` (Numeric(10,2))
- `grade_scale_id`
- `created_at`, `updated_at`

#### `marks_yearly`
Calculated yearly exam results.

**Columns:**
- `id` (PK)
- `exam_name`
- `student_id`
- `program_id`, `grade_id`, `grade_group_id`, `academic_id`
- `marks_system_id`
- `marks_isemester_ids` (Text, comma-separated) ⚠️ **Note: "i" before "semester"**
- `total` (Numeric(10,2))
- `average` (Numeric(10,2))
- `grade_scale_id`
- `created_at`, `updated_at`

#### `exam_calculate_sign`
Calculation configuration rules.

**Columns:**
- `id` (PK)
- `result_name` (exam name)
- `exam_type` ('input', 'semester', 'yearly')
- `formula_expression` (e.g., "1+2+3" or "(57+58)+62")
- `marks_system_id`
- `academic_id`, `program_id`, `grade_group_id`
- `divide_by_multiplier` (Numeric(10,2)) ⚠️ **Critical column**
- `is_active`
- `created_at`, `updated_at`

#### `subjects_group`
Subject configuration.

**Columns:**
- `id` (PK)
- `subject_id`
- `academic_id`, `program_id`, `grade_group_id`
- `full_marks` (Numeric(10,2))
- `calculate_marks` (Numeric(10,2)) - percentage deduction
- `created_at`, `updated_at`

#### `grade_scale`
Grade scale definitions.

**Columns:**
- `id` (PK)
- `academic_id`, `grade_group_id`
- `us_grade` (String) - A, B, C, D, E, F
- `kh_grade` (String) - Khmer grade
- `min_marks` (Numeric(10,2))
- `max_marks` (Numeric(10,2))
- `is_overall`
- `created_at`, `updated_at`

### Important Column Names

⚠️ **Critical:** The database uses these exact column names:
- `marks_semester.marks_imonthly_ids` (with "i" before "monthly")
- `marks_yearly.marks_isemester_ids` (with "i" before "semester")

These are **NOT** `marks_monthly_ids` or `marks_semester_ids`!

---

## API Endpoints

### GET `/api/v1/marks/exams`
Get available exams for a class with availability status.

**Query Parameters:**
- `program_id` (required)
- `grade_id` (required)
- `grade_type_id` (optional)
- `academic_id` (required)

**Response:**
```json
{
  "success": true,
  "exams": [
    {
      "id": 1,
      "name": "Monthly Exam 1",
      "academic_id": 1,
      "is_available": true,
      "reason": null,
      "for_month": "2024-01-01",
      "start_date": "2024-01-01",
      "deadline": "2024-01-11",
      "extra_days": 0
    }
  ]
}
```

**Availability Logic:**
- Available if: `for_month <= current_date <= deadline`
- Deadline = `for_month + 10 days + extra_days`
- "Soon" if before `for_month`
- "Deadline passed" if after `deadline`

### GET `/api/v1/marks/subjects`
Get subjects for an exam.

**Query Parameters:**
- `program_id`, `grade_id`, `grade_type_id`, `academic_id` (required)
- `marks_system_id` (required)

**Response:**
```json
{
  "success": true,
  "subjects": [
    {
      "id": 1,
      "name": "Mathematics",
      "full_marks": 100.0,
      "calculate_marks": 100.0
    }
  ]
}
```

### GET `/api/v1/marks/students`
Get students with existing marks for a subject.

**Query Parameters:**
- `program_id`, `grade_id`, `grade_type_id`, `academic_id` (required)
- `marks_system_id`, `subject_id` (required)

**Response:**
```json
{
  "success": true,
  "students": [
    {
      "id": 1,
      "student_id": "STD001",
      "kName": "សិស្ស",
      "eName": "Student",
      "gender": "Male",
      "current_mark": 85.5,
      "mark_id": 123
    }
  ]
}
```

### POST `/api/v1/marks/save`
Save marks and trigger calculations.

**Request Body:**
```json
{
  "program_id": 1,
  "grade_id": 1,
  "grade_type_id": 1,
  "academic_id": 1,
  "marks_system_id": 1,
  "subject_id": 1,
  "marks": [
    {
      "student_id": 1,
      "mark": 85.5,
      "mark_id": 123
    },
    {
      "student_id": 2,
      "mark": 90.0
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "saved": 1,
  "updated": 1,
  "total": 2
}
```

**Process:**
1. Validate month-based deadline
2. For each mark:
   - If `mark_id` exists → UPDATE
   - Else → DELETE old + INSERT new (prevents duplicates)
3. Trigger calculations (monthly → semester → yearly)
4. Single COMMIT

---

## Transaction Safety

### Single Transaction Pattern

All operations (marks_input + calculations) happen in **one transaction**:

```python
try:
    # 1. Save marks_input
    for mark in marks_list:
        if mark_id:
            UPDATE marks_input
        else:
            DELETE old + INSERT new
    
    # 2. Trigger calculations (auto_commit=False)
    monthly_ids = await calculate_and_store_monthly_marks(..., auto_commit=False)
    semester_ids = await calculate_and_store_semester_marks(..., auto_commit=False)
    yearly_ids = await calculate_and_store_yearly_marks(..., auto_commit=False)
    
    # 3. Single commit
    db.commit()
    
except Exception:
    db.rollback()
    raise
```

### Why This Matters

- **Atomicity:** All or nothing - if any step fails, everything rolls back
- **Data Integrity:** No partial updates
- **Consistency:** All related tables stay in sync

### Duplicate Prevention

Before inserting new marks:
```sql
DELETE FROM marks_input 
WHERE student_id = ? AND academic_id = ? AND program_id = ? 
  AND grade_id = ? AND subject_id = ? AND marks_system_id = ?
```

This ensures no duplicate marks for the same student/subject/exam combination.

---

## Developer Guide

### Adding a New Calculation Type

1. **Add to `exam_calculate_sign`:**
   - Set `exam_type` ('input', 'semester', 'yearly')
   - Set `formula_expression` (e.g., "1+2+3")
   - Set `divide_by_multiplier`

2. **Update calculation function** (if needed):
   - Modify `calculate_and_store_*_marks()` in `marks_calculations.py`

3. **Test:**
   - Verify calculations match expected results
   - Check transaction rollback on errors

### Debugging Calculations

**Enable logging:**
```python
import logging
logging.getLogger('app.services.marks_calculations').setLevel(logging.DEBUG)
```

**Key log messages:**
- `"Recalculated for student X, exam Y: adjusted_total_marks=Z, raw_average=W"`
- `"Semester calculation for student X: found_grouped_exams=Y, adjusted=Z"`

**Check database:**
```sql
-- Check monthly calculation
SELECT * FROM marks_monthly WHERE student_id = ? AND exam_name = ?;

-- Check semester calculation
SELECT * FROM marks_semester WHERE student_id = ? AND exam_name = ?;

-- Check yearly calculation
SELECT * FROM marks_yearly WHERE student_id = ? AND exam_name = ?;
```

### Common Issues

#### Issue 1: Wrong Column Names
**Symptom:** SQL errors about missing columns

**Solution:** Ensure database has:
- `marks_imonthly_ids` (not `marks_monthly_ids`)
- `marks_isemester_ids` (not `marks_semester_ids`)

#### Issue 2: Calculation Returns 0
**Symptom:** All averages are 0

**Check:**
- `divide_by_multiplier` is set in `exam_calculate_sign`
- `formula_expression` has correct subject/exam IDs
- Student has marks in `marks_input`

#### Issue 3: Transaction Errors
**Symptom:** Partial updates, data inconsistency

**Solution:** Ensure `auto_commit=False` when calling calculation functions from `save_marks`

### Testing Checklist

- [ ] Mark entry within deadline works
- [ ] Mark entry after deadline is rejected
- [ ] Monthly calculation is correct
- [ ] Semester calculation (Khmer) is correct
- [ ] Semester calculation (English/IEP) is correct
- [ ] Yearly calculation is correct
- [ ] Transaction rollback works on error
- [ ] Duplicate prevention works
- [ ] Grade scale lookup is correct

---

## Related Documentation

- [Deep Verification Report](./DEEP_VERIFICATION_REPORT.md) - Detailed comparison with Telegram bot
- [API Reference](./API_REFERENCE.md) - Complete API documentation
- [Database Schema](./DATABASE_SCHEMA.md) - Full database schema

---

## Support

For questions or issues:
1. Check this documentation
2. Review the code comments
3. Check the verification report for implementation details
4. Contact the development team

---

**Last Updated:** 2024
**Version:** 1.0

