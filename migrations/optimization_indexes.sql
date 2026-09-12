-- Performance Optimization Indexes
-- Run this on your MySQL database to improve query performance

-- Users table indexes
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_phone ON users(phone);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_workplace ON users(workplace);

-- Parents table indexes
CREATE INDEX idx_parents_username ON parents(username);
CREATE INDEX idx_parents_father_phone ON parents(fatherPhone);
CREATE INDEX idx_parents_mother_phone ON parents(motherPhone);
CREATE INDEX idx_parents_gphone ON parents(gPhone);
CREATE INDEX idx_parents_status ON parents(status);

-- Students table indexes (find the actual column names)
-- CREATE INDEX idx_students_username ON students(username);
-- CREATE INDEX idx_students_studentid ON students(studentid);

-- Role permissions indexes
CREATE INDEX idx_role_permissions_role_id ON role_permissions(role_id);
CREATE INDEX idx_role_permissions_permission_id ON role_permissions(permission_id);

-- Device tokens indexes
CREATE INDEX idx_device_tokens_user ON device_tokens(user_id, user_type);
