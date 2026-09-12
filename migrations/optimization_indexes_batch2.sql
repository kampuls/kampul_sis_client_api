-- Performance Optimization Indexes - Batch 2
-- Run this on your MySQL database: mysql -u root pama_school < optimization_indexes_batch2.sql

-- ============================================
-- CRITICAL: Attendance table indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_attendance_student_date 
ON daily_attendance(student_id, attendance_date);

CREATE INDEX IF NOT EXISTS idx_attendance_program_grade_shift 
ON daily_attendance(program_id, grade_id, shift_id, academic_id);

CREATE INDEX IF NOT EXISTS idx_attendance_academic 
ON daily_attendance(academic_id);

-- ============================================
-- CRITICAL: Learning table indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_learning_student_academic 
ON learning(studentid, academicid);

CREATE INDEX IF NOT EXISTS idx_learning_grade_shift 
ON learning(gradeid, shiftid);

CREATE INDEX IF NOT EXISTS idx_learning_program 
ON learning(programid);

-- ============================================
-- CRITICAL: Class teachers indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_class_teachers_teacher_academic 
ON class_teachers(teacher_id, academic_id);

CREATE INDEX IF NOT EXISTS idx_class_teachers_grade_shift 
ON class_teachers(grade_id, shift_id, academic_id);

-- ============================================
-- Marks system indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_marks_input_student_academic 
ON marks_input(student_id, academic_id);

CREATE INDEX IF NOT EXISTS idx_marks_input_marks_system 
ON marks_input(marks_system_id, student_id);

CREATE INDEX IF NOT EXISTS idx_marks_definitions_grade_group 
ON marks_definitions(grade_group, academic_id);

-- ============================================
-- Students table indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_students_branch_status 
ON students(branch, status);

CREATE INDEX IF NOT EXISTS idx_students_academic 
ON students(academic);

CREATE INDEX IF NOT EXISTS idx_students_program_grade 
ON students(programid, gradeid);

-- ============================================
-- Parents table - optimize myChilds lookups
-- ============================================
-- Note: myChilds uses FIND_IN_SET which can't use indexes
-- Consider normalizing to a junction table for better performance

-- ============================================
-- Events and Forms indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_events_hot_createdat 
ON events(is_hot, created_at);

CREATE INDEX IF NOT EXISTS idx_forms_program_grade 
ON forms(program, grade, shift);

-- ============================================
-- Holiday indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_holiday_dates 
ON holiday_tbl(start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_holiday_program_grade_shift 
ON holiday_tbl(program, grade, shift);

-- ============================================
-- Fee services indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_fee_services_grade_program 
ON fee_services(grade, program);

-- ============================================
-- Composite index for auth me endpoint
-- ============================================
CREATE INDEX IF NOT EXISTS idx_users_workplace_role_status 
ON users(workplace, role, status);
