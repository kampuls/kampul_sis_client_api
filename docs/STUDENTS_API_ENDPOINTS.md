# Students Management API Endpoints

This document describes the API endpoints required for the Students Management screen in the Flutter application.

## Base URL
```
/api/v1
```

## Authentication
All endpoints require Bearer token authentication:
```
Authorization: Bearer <access_token>
```

---

## 1. Get All Students
**Endpoint:** `GET /students`

**Description:** Retrieve all students with optional filters

**Query Parameters:**
- `branch_id` (optional): Filter by branch ID
- `program_id` (optional): Filter by program ID
- `shift_id` (optional): Filter by shift ID
- `gender` (optional): Filter by gender (Male, Female, ប្រុស, ស្រី)
- `status` (optional): Filter by status (active, inactive)
- `search` (optional): Search by name, student ID, or branch name

**Response:**
```json
{
  "students": [
    {
      "id": 1,
      "studentid": "ST001",
      "optional_id": "OPT001",
      "username": "student1",
      "kName": "សុខ វឌ្ឍនា",
      "eName": "Sok Vatthana",
      "gender": "ប្រុស",
      "dob": "2010-05-15",
      "image": null,
      "student_phone": "0123456789",
      "is_foreigner": 0,
      "province": "Phnom Penh",
      "district": "Chamkar Mon",
      "commune": "Tonle Bassac",
      "village": "Village 1",
      "previousSchool": null,
      "leaveDate": null,
      "myparents": 1,
      "child_order": 1,
      "academic": 2,
      "branch": 1,
      "status": "active",
      "student_noted": null,
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T00:00:00",
      "program_name": "IEP",
      "grade_name": "Kindergarten I",
      "shift_name": "វេនរសៀល (PM)",
      "branch_name": "ឃ្លាំងលើ (KL)",
      "age": 14
    }
  ],
  "total": 100,
  "message": "Students retrieved successfully"
}
```

---

## 2. Get Student by ID
**Endpoint:** `GET /students/{student_id}`

**Description:** Get detailed information about a specific student

**URL Parameters:**
- `student_id`: The ID of the student

**Response:**
```json
{
  "student": {
    "id": 1,
    "studentid": "ST001",
    ...
    "age": 14
  },
  "message": "Student retrieved successfully"
}
```

---

## 3. Get Student Summary/Statistics
**Endpoint:** `GET /students/summary`

**Description:** Get aggregated statistics about students

**Query Parameters:**
- `branch_id` (optional): Filter by branch ID
- `academic_id` (optional): Filter by academic year ID

**Response:**
```json
{
  "summary": {
    "total_students": 1234,
    "male_count": 650,
    "female_count": 584,
    "foreigner_count": 45,
    "active_count": 1200,
    "inactive_count": 34,
    "by_program": {
      "IEP": 500,
      "BEP": 450,
      "Montessori": 284
    },
    "by_shift": {
      "វេនព្រឹក (AM)": 600,
      "វេនរសៀល (PM)": 634
    },
    "by_branch": {
      "ឃ្លាំងលើ (KL)": 400,
      "សែនសុខ (SS)": 834
    },
    "by_age": {
      "3": 50,
      "4": 100,
      "5": 150,
      ...
    }
  },
  "message": "Summary retrieved successfully"
}
```

---

## 4. Get Parent Information
**Endpoint:** `GET /parents/{parent_id}`

**Description:** Get parent/guardian information

**URL Parameters:**
- `parent_id`: The ID of the parent

**Response:**
```json
{
  "parent": {
    "id": 1,
    "uniqueid": "P001",
    "username": "parent1",
    "fatherName": "Father Name",
    "motherName": "Mother Name",
    "fatherPhone": "0123456789",
    "motherPhone": "0987654321",
    "fatherJob": "Engineer",
    "motherJob": "Teacher",
    "pProvince": "Phnom Penh",
    "pDistrict": "Chamkar Mon",
    "pCommune": "Tonle Bassac",
    "pVillage": "Village 1",
    "pEmail": "parent@example.com",
    "pTelegramId": null,
    "gName": "Guardian Name",
    "gPhone": "0123456789",
    "gIsThe": "Uncle",
    "gHome": "House 123",
    "gStreet": "Street 456",
    "gGroup": "Group 5",
    "gProvince": "Phnom Penh",
    "gDistrict": "Chamkar Mon",
    "gCommune": "Tonle Bassac",
    "gVillage": "Village 1",
    "myChilds": "1,2,3",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00"
  },
  "message": "Parent retrieved successfully"
}
```

---

## 5. Get Students by Parent
**Endpoint:** `GET /parents/{parent_id}/students`

**Description:** Get all students for a specific parent

**URL Parameters:**
- `parent_id`: The ID of the parent

**Response:**
```json
{
  "students": [
    {
      "id": 1,
      "studentid": "ST001",
      ...
    }
  ],
  "total": 3,
  "message": "Students retrieved successfully"
}
```

---

## 6. Get All Branches
**Endpoint:** `GET /branches`

**Description:** Get all branches for filtering

**Response:**
```json
{
  "branches": [
    {
      "id": 1,
      "branch_name": "ឃ្លាំងលើ (KL)",
      "branch_code": "KL"
    }
  ]
}
```

---

## 7. Get All Programs
**Endpoint:** `GET /programs`

**Description:** Get all programs for filtering

**Response:**
```json
{
  "programs": [
    {
      "id": 1,
      "program_name": "IEP",
      "program_code": "IEP"
    }
  ]
}
```

---

## 8. Get All Shifts
**Endpoint:** `GET /shifts`

**Description:** Get all shifts for filtering

**Response:**
```json
{
  "shifts": [
    {
      "id": 1,
      "shift_name": "វេនព្រឹក (AM)",
      "shift_code": "AM",
      "start_at": "07:00:00",
      "end_at": "11:00:00"
    }
  ]
}
```

---

## Implementation Notes

### SQL Queries

#### Get Students with Details
```sql
SELECT 
    s.*,
    p.program_name,
    g.grade_name,
    sh.shift_name,
    b.branch_name,
    TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) as age
FROM students s
LEFT JOIN programs p ON s.program = p.id
LEFT JOIN grades g ON s.grade = g.id
LEFT JOIN shifts sh ON s.shift = sh.id
LEFT JOIN branches b ON s.branch = b.id
WHERE s.status = 'active'
  AND (? IS NULL OR s.branch = ?)
  AND (? IS NULL OR s.gender = ?)
  AND (? IS NULL OR s.kName LIKE ? OR s.eName LIKE ? OR s.studentid LIKE ?)
ORDER BY s.kName ASC
```

#### Get Summary Statistics
```sql
SELECT 
    COUNT(*) as total_students,
    SUM(CASE WHEN gender IN ('ប្រុស', 'Male', 'M') THEN 1 ELSE 0 END) as male_count,
    SUM(CASE WHEN gender IN ('ស្រី', 'Female', 'F') THEN 1 ELSE 0 END) as female_count,
    SUM(CASE WHEN is_foreigner = 1 THEN 1 ELSE 0 END) as foreigner_count,
    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_count,
    SUM(CASE WHEN status = 'inactive' THEN 1 ELSE 0 END) as inactive_count
FROM students
WHERE (? IS NULL OR branch = ?)
  AND (? IS NULL OR academic = ?)
```

#### Get Students by Program
```sql
SELECT 
    p.program_name,
    COUNT(*) as count
FROM students s
LEFT JOIN programs p ON s.program = p.id
WHERE (? IS NULL OR s.branch = ?)
GROUP BY p.program_name
```

### Error Handling
- Return 404 if student/parent not found
- Return 401 for unauthorized access
- Return 400 for invalid parameters
- Return 500 for server errors

### Performance Considerations
- Add indexes on: `branch`, `program`, `shift`, `gender`, `status`, `studentid`
- Add composite index on `(branch, status, academic)`
- Cache summary statistics for 5 minutes
- Use pagination for large result sets (add `page` and `limit` parameters)

### Security
- Teachers can only see students from their branch (based on `workplace`)
- Admins can see all students
- Validate all input parameters
- Sanitize search queries to prevent SQL injection

