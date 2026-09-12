-- Kampul SIS School Tenant Database Template
-- Contains full 212 tables and core default/seed reference data

SET FOREIGN_KEY_CHECKS = 0;
SET NAMES utf8mb4;

-- ==========================================
-- 1. DDL: CREATE ALL 212 TABLES
-- ==========================================

CREATE TABLE IF NOT EXISTS `_schema_patches` (
  `patch_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`patch_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `academic` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academic_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `academic_us_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `academic_start` date NOT NULL,
  `academic_end` date NOT NULL,
  `quarter_one_start` date DEFAULT NULL,
  `quarter_one_end` date DEFAULT NULL,
  `quarter_two_start` date DEFAULT NULL,
  `quarter_two_end` date DEFAULT NULL,
  `quarter_three_start` date DEFAULT NULL,
  `quarter_three_end` date DEFAULT NULL,
  `quarter_four_start` date DEFAULT NULL,
  `quarter_four_end` date DEFAULT NULL,
  `semester_one_start` date DEFAULT NULL,
  `semester_one_end` date DEFAULT NULL,
  `semester_two_start` date DEFAULT NULL,
  `semester_two_end` date DEFAULT NULL,
  `status` tinyint(1) NOT NULL,
  `isUsed` tinyint(1) NOT NULL,
  `isUsed_at` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `academic_program_images` (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_id` int NOT NULL,
  `image_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `position` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `program_id` (`program_id`) USING BTREE,
  KEY `ix_academic_program_images_id` (`id`) USING BTREE,
  CONSTRAINT `academic_program_images_ibfk_1` FOREIGN KEY (`program_id`) REFERENCES `academic_programs` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `academic_programs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `icon_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `custom_logo_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `color_start` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `color_end` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sort_order` int DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `contact_phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `contact_email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `facebook_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `telegram_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `youtube_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `tiktok_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `registration_start_date` date DEFAULT NULL,
  `registration_end_date` date DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_academic_programs_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `accounts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `account_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `account_number` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `qr_code` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `branch_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `balance` decimal(65,2) DEFAULT NULL,
  `currency` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bank_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ad_clicks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ad_id` int NOT NULL,
  `user_id` int DEFAULT NULL COMMENT 'User who clicked (if logged in)',
  `user_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'teacher, student, parent, guest',
  `clicked_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `device_info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Device type, OS, etc.',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_ad` (`ad_id`) USING BTREE,
  KEY `idx_user` (`user_id`) USING BTREE,
  KEY `idx_date` (`clicked_at`) USING BTREE,
  CONSTRAINT `fk_ad_clicks_ad_id` FOREIGN KEY (`ad_id`) REFERENCES `ads` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=119 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `admin_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `action` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `details` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `timestamp` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_admin_logs_user` (`user_id`) USING BTREE,
  KEY `idx_admin_logs_action` (`action`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ads` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Ad title (e.g., "New Academic Year Registration")',
  `subtitle` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Short subtitle or tagline',
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Full description shown in detail screen',
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Path to image file (e.g., "/uploads/ads/banner_001.jpg")',
  `image_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Full server path if needed',
  `ad_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'general' COMMENT 'Type: general, registration, event, announcement, promotion',
  `action_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Action: register, navigate, external_link, none',
  `action_data` json DEFAULT NULL COMMENT 'Action parameters (e.g., {"route": "registration", "params": {...}})',
  `button_text` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Button text (e.g., "Register Now", "Learn More")',
  `button_color` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT '#1976D2' COMMENT 'Button color in hex',
  `target_audience` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'all' COMMENT 'all, teachers, students, parents, staff',
  `start_date` datetime DEFAULT NULL COMMENT 'When ad should start showing',
  `end_date` datetime DEFAULT NULL COMMENT 'When ad should stop showing',
  `is_active` tinyint(1) DEFAULT '1' COMMENT '1 = active, 0 = inactive',
  `display_order` int DEFAULT '0' COMMENT 'Order for display (lower = first)',
  `click_count` int DEFAULT '0' COMMENT 'Number of times ad was clicked',
  `view_count` int DEFAULT '0' COMMENT 'Number of times ad was viewed',
  `created_by` int DEFAULT NULL COMMENT 'User ID who created the ad',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `academic_id` int DEFAULT NULL COMMENT 'Filter by academic year',
  `branch_id` int DEFAULT NULL COMMENT 'Filter by branch (NULL = all branches)',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_active` (`is_active`,`start_date`,`end_date`) USING BTREE,
  KEY `idx_display_order` (`display_order`) USING BTREE,
  KEY `idx_academic` (`academic_id`) USING BTREE,
  KEY `idx_branch` (`branch_id`) USING BTREE,
  KEY `idx_type` (`ad_type`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=36 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_conversations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `role_id` int DEFAULT NULL,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `is_pinned` tinyint(1) DEFAULT NULL,
  `is_deleted` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_ai_conversations_id` (`id`) USING BTREE,
  KEY `ix_ai_conversations_user_id` (`user_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_messages` (
  `id` int NOT NULL AUTO_INCREMENT,
  `conversation_id` int NOT NULL,
  `role` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `conversation_id` (`conversation_id`) USING BTREE,
  KEY `ix_ai_messages_id` (`id`) USING BTREE,
  CONSTRAINT `ai_messages_ibfk_1` FOREIGN KEY (`conversation_id`) REFERENCES `ai_conversations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=46 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `alembic_version` (
  `version_num` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`version_num`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `app_admins` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `is_super_admin` tinyint(1) NOT NULL,
  `is_locked` tinyint(1) NOT NULL,
  `locked_at` datetime DEFAULT NULL,
  `locked_by` int DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime DEFAULT NULL,
  `can_reset_attendance_devices` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `ix_app_admins_user_id` (`user_id`) USING BTREE,
  KEY `locked_by` (`locked_by`) USING BTREE,
  KEY `ix_app_admins_id` (`id`) USING BTREE,
  CONSTRAINT `app_admins_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `app_admins_ibfk_2` FOREIGN KEY (`locked_by`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `app_branding_settings` (
  `id` int NOT NULL,
  `icon_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'school_rounded',
  `top_text` varchar(80) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'PAMA',
  `bottom_text` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'INTERNATIONAL SCHOOL',
  `icon_background_color` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '#1E5BD8',
  `icon_color` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '#FFFFFF',
  `top_text_color` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '#22252A',
  `bottom_text_color` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '#6F7280',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `icon_background_color_dark` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `icon_color_dark` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `top_text_color_dark` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bottom_text_color_dark` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `use_logo_image` tinyint(1) NOT NULL DEFAULT '0',
  `logo_image_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `logo_image_url_dark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `app_quick_action_settings` (
  `id` int NOT NULL,
  `items_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `stuid` int DEFAULT NULL,
  `morning_in` tinyint(1) DEFAULT '0',
  `morning_time_in` time DEFAULT NULL,
  `morning_out` tinyint(1) DEFAULT '0',
  `morning_time_out` time DEFAULT NULL,
  `morning_leave_early` tinyint(1) DEFAULT NULL,
  `afternoon_in` tinyint(1) DEFAULT '0',
  `afternoon_time_in` time DEFAULT NULL,
  `afternoon_out` tinyint(1) DEFAULT '0',
  `afternoon_time_out` time DEFAULT NULL,
  `afternoon_leave_early` tinyint(1) DEFAULT NULL,
  `attendance_date` date DEFAULT NULL,
  `academic` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `last_update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=191 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance__allowed_branches` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_attendance__allowed_branches_branch_id` (`branch_id`) USING BTREE,
  KEY `ix_attendance__allowed_branches_user_id` (`user_id`) USING BTREE,
  KEY `ix_attendance__allowed_branches_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=776 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_audience_presets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preset_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `branch_id` int DEFAULT NULL,
  `department_id` int DEFAULT NULL,
  `is_foreigner` int DEFAULT NULL,
  `employee_ids_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_attendance_audience_preset_owner_name` (`created_by`,`name`) USING BTREE,
  KEY `ix_attendance_audience_presets_preset_type` (`preset_type`) USING BTREE,
  KEY `ix_attendance_audience_presets_is_foreigner` (`is_foreigner`) USING BTREE,
  KEY `ix_attendance_audience_presets_created_by` (`created_by`) USING BTREE,
  KEY `ix_attendance_audience_presets_department_id` (`department_id`) USING BTREE,
  KEY `ix_attendance_audience_presets_branch_id` (`branch_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_audit_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `user_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_role` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `action_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_id` int NOT NULL,
  `old_value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `new_value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `change_description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `student_id` int DEFAULT NULL,
  `student_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `class_id` int DEFAULT NULL,
  `class_description` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `created_at_khmer` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ip_address` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_agent` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_attendance_audit_log_id` (`id`) USING BTREE,
  KEY `ix_attendance_audit_log_student_id` (`student_id`) USING BTREE,
  KEY `ix_attendance_audit_log_branch_id` (`branch_id`) USING BTREE,
  KEY `ix_attendance_audit_log_user_id` (`user_id`) USING BTREE,
  KEY `ix_attendance_audit_log_created_at` (`created_at`) USING BTREE,
  CONSTRAINT `attendance_audit_log_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `attendance_audit_log_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=100247 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `scan_time` datetime NOT NULL,
  `scan_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'arrival',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_attendance_log_student_time` (`student_id`,`scan_time`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_primary_device_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `action` varchar(40) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_user_id` int DEFAULT NULL,
  `previous_device_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `new_device_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `detail_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_attendance_primary_device_events_created_at` (`created_at`) USING BTREE,
  KEY `ix_attendance_primary_device_events_action` (`action`) USING BTREE,
  KEY `ix_attendance_primary_device_events_actor_user_id` (`actor_user_id`) USING BTREE,
  KEY `ix_attendance_primary_device_events_user_id` (`user_id`) USING BTREE,
  CONSTRAINT `attendance_primary_device_events_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `attendance_primary_device_events_ibfk_2` FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=173 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_primary_devices` (
  `user_id` int NOT NULL,
  `device_id_hash` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `device_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `platform` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `registered_at` datetime NOT NULL,
  `last_changed_at` datetime NOT NULL,
  `change_available_at` datetime NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`) USING BTREE,
  KEY `ix_attendance_primary_devices_change_available_at` (`change_available_at`) USING BTREE,
  KEY `ix_attendance_primary_devices_device_id_hash` (`device_id_hash`) USING BTREE,
  CONSTRAINT `attendance_primary_devices_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_processing_rules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `scope_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope_id` int NOT NULL,
  `is_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `updated_by` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_attendance_processing_scope` (`scope_type`,`scope_id`) USING BTREE,
  KEY `ix_attendance_processing_rules_scope_id` (`scope_id`) USING BTREE,
  KEY `ix_attendance_processing_rules_scope_type` (`scope_type`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `check_in_time` datetime DEFAULT NULL,
  `check_out_time` datetime DEFAULT NULL,
  `check_in_latitude` float(10,8) DEFAULT NULL,
  `check_in_longitude` float(11,8) DEFAULT NULL,
  `check_out_latitude` float(10,8) DEFAULT NULL,
  `check_out_longitude` float(11,8) DEFAULT NULL,
  `is_mock_location` tinyint(1) DEFAULT '0',
  `device_info` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `attendance_date` date NOT NULL,
  `work_hours` float DEFAULT NULL,
  `status` enum('present','absent','half_day','late','early_leave') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'present',
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `late_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `leave_early_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `check_in_branch_id` int DEFAULT NULL,
  `check_out_branch_id` int DEFAULT NULL,
  `earned_percentage` float DEFAULT NULL,
  `session_index` int DEFAULT NULL,
  `schedule_id` int DEFAULT NULL,
  `scheduled_start` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `scheduled_end` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `snapshot_late_grace_minutes` int DEFAULT NULL,
  `snapshot_allow_early_leave_mins` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_attendance_user` (`user_id`) USING BTREE,
  KEY `idx_attendance_date` (`attendance_date`) USING BTREE,
  KEY `idx_attendance_status` (`status`) USING BTREE,
  KEY `idx_attendance_records_session_index` (`session_index`) USING BTREE,
  KEY `idx_attendance_records_schedule_id` (`schedule_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=15065 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_schedule_exception_enrollments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exception_id` int NOT NULL,
  `user_id` int NOT NULL,
  `occurrence_date` date NOT NULL,
  `enrolled_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_attendance_exception_enrollment_user_date` (`user_id`,`occurrence_date`) USING BTREE,
  KEY `ix_attendance_schedule_exception_enrollments_user_id` (`user_id`) USING BTREE,
  KEY `ix_attendance_schedule_exception_enrollments_occurrence_date` (`occurrence_date`) USING BTREE,
  KEY `ix_attendance_schedule_exception_enrollments_id` (`id`) USING BTREE,
  KEY `ix_attendance_schedule_exception_enrollments_exception_id` (`exception_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=155 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_schedule_exceptions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exception_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  `user_id` int DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `department_id` int DEFAULT NULL,
  `is_foreigner` int DEFAULT NULL,
  `exception_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `sessions` json DEFAULT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_by` int DEFAULT NULL,
  `is_active` int DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `recurrence_type` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title_en` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title_km` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reason_en` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reason_km` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `self_enrollment_enabled` int NOT NULL,
  `allow_outside_workplace` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_attendance_schedule_exceptions_is_foreigner` (`is_foreigner`) USING BTREE,
  KEY `ix_attendance_schedule_exceptions_id` (`id`) USING BTREE,
  KEY `ix_attendance_schedule_exceptions_user_id` (`user_id`) USING BTREE,
  KEY `ix_attendance_schedule_exceptions_branch_id` (`branch_id`) USING BTREE,
  KEY `ix_attendance_schedule_exceptions_end_date` (`end_date`) USING BTREE,
  KEY `ix_attendance_schedule_exceptions_department_id` (`department_id`) USING BTREE,
  KEY `ix_attendance_schedule_exceptions_exception_date` (`exception_date`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_schedules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'standard',
  `branch_id` int DEFAULT NULL,
  `department_id` int DEFAULT NULL,
  `user_id` int DEFAULT NULL,
  `weekly_config` json NOT NULL,
  `is_active` int DEFAULT '1',
  `effective_date` date NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_default` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_schedule_branch` (`branch_id`) USING BTREE,
  KEY `idx_schedule_dept` (`department_id`) USING BTREE,
  KEY `idx_schedule_user` (`user_id`) USING BTREE,
  KEY `idx_schedule_active` (`is_active`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=44 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_statistics` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `shift_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `statistic_date` date NOT NULL,
  `day_of_week` int NOT NULL,
  `month` int NOT NULL,
  `year` int NOT NULL,
  `first_attendance_time` datetime DEFAULT NULL,
  `last_attendance_time` datetime DEFAULT NULL,
  `average_attendance_time` datetime DEFAULT NULL,
  `first_attendance_minutes` int DEFAULT NULL,
  `last_attendance_minutes` int DEFAULT NULL,
  `average_attendance_minutes` float DEFAULT NULL,
  `total_students` int DEFAULT NULL,
  `marked_present` int DEFAULT NULL,
  `marked_absent` int DEFAULT NULL,
  `marked_late` int DEFAULT NULL,
  `marked_permission` int DEFAULT NULL,
  `primary_teacher_id` int DEFAULT NULL,
  `primary_teacher_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `peak_hour` int DEFAULT NULL,
  `peak_hour_count` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  `statistic_date_khmer` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `primary_teacher_id` (`primary_teacher_id`) USING BTREE,
  KEY `ix_attendance_statistics_branch_id` (`branch_id`) USING BTREE,
  KEY `ix_attendance_statistics_grade_id` (`grade_id`) USING BTREE,
  KEY `ix_attendance_statistics_shift_id` (`shift_id`) USING BTREE,
  KEY `ix_attendance_statistics_academic_id` (`academic_id`) USING BTREE,
  KEY `ix_attendance_statistics_program_id` (`program_id`) USING BTREE,
  KEY `ix_attendance_statistics_statistic_date` (`statistic_date`) USING BTREE,
  KEY `ix_attendance_statistics_year` (`year`) USING BTREE,
  KEY `ix_attendance_statistics_id` (`id`) USING BTREE,
  KEY `ix_attendance_statistics_month` (`month`) USING BTREE,
  CONSTRAINT `attendance_statistics_ibfk_1` FOREIGN KEY (`primary_teacher_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=4936 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_system_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `require_location` tinyint(1) DEFAULT '1',
  `block_mock_location` tinyint(1) DEFAULT '1',
  `block_developer_options` tinyint(1) DEFAULT '0',
  `allowed_ip_ranges` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `allow_early_clock_in_mins` int DEFAULT NULL,
  `allow_late_clock_out_mins` int DEFAULT NULL,
  `late_grace_minutes` int NOT NULL DEFAULT '15' COMMENT 'Grace period before marking as late',
  `updated_at` date DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `per_session_early_clock_in_mins` json DEFAULT NULL,
  `min_minutes_before_checkout` int NOT NULL,
  `allow_early_leave_mins` int NOT NULL,
  `allow_makeup_missing_sessions` tinyint(1) NOT NULL,
  `notify_enable_before` tinyint(1) NOT NULL,
  `notify_minutes_before` json DEFAULT NULL,
  `notify_enable_after` tinyint(1) NOT NULL,
  `notify_minutes_after` json DEFAULT NULL,
  `notify_enable_before_checkout` tinyint(1) NOT NULL,
  `notify_minutes_before_checkout` json DEFAULT NULL,
  `notify_enable_after_checkout` tinyint(1) NOT NULL,
  `notify_minutes_after_checkout` json DEFAULT NULL,
  `session_transition_wait_mins` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_user_assignments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `schedule_id` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `assigned_by` int DEFAULT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `start_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_user_schedule` (`user_id`,`schedule_id`) USING BTREE,
  KEY `idx_assignment_user` (`user_id`) USING BTREE,
  KEY `idx_assignment_schedule` (`schedule_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=581 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `background_cards` (
  `id` int NOT NULL AUTO_INCREMENT,
  `front_image` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `back_image` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `card_model` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `background_cert` (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `cer_model` int DEFAULT NULL,
  `background_image` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `grade_group_ids` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `grade_ids` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `background_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `orientation` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'landscape',
  `signature_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `stamp_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bonus_deduction_rules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `calculation_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `amount` decimal(12,2) NOT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_rules_type` (`type`) USING BTREE,
  KEY `idx_rules_calculation` (`calculation_type`) USING BTREE,
  KEY `idx_rules_active` (`is_active`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `branch` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `contact` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `address_khmer` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `address_english` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `website` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `id_prefix` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `id_start_number` int DEFAULT '1',
  `id_digit` int DEFAULT '10',
  `id_reset_option` enum('month','year','auto') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'auto',
  `report_time` time DEFAULT NULL,
  `users_id` int DEFAULT NULL,
  `report_weekend` enum('yes','no') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'no',
  `report_status` enum('yes','no') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'no',
  `invoice_prefix` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `invoice_digit` int DEFAULT NULL,
  `invoice_start_number` int DEFAULT NULL,
  `invoice_reset_december` int DEFAULT '0',
  `vatin_number` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `receipt_digit` int DEFAULT NULL,
  `receipt_prefix` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `receipt_start_number` int DEFAULT NULL,
  `receipt_reset_option` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `receipt_header` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `image_header` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `director_kName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `director_eName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `director_signature` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `stamp` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `headTeacher_kName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `headTeacher_eName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `headTeacher_signature` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `app_display_name` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `app_branch_cover` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `app_branch_facebook_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `app_branch_telegram_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `app_branch_youtube_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `app_branch_tiktok_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `app_branch_google_map_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `map_latitude` double DEFAULT NULL,
  `map_longitude` double DEFAULT NULL,
  `open_at` time DEFAULT NULL,
  `close_at` time DEFAULT NULL,
  `pickup_radius_meters` decimal(12,2) DEFAULT '100.00',
  `image_header_path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `director_signature_path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `headTeacher_signature_path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `stamp_path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `signature_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `stamp_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `branch_contacts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_id` int NOT NULL,
  `label` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_branch_contacts_id` (`id`) USING BTREE,
  KEY `ix_branch_contacts_branch_id` (`branch_id`) USING BTREE,
  CONSTRAINT `branch_contacts_ibfk_1` FOREIGN KEY (`branch_id`) REFERENCES `branch` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bus_assignment_assistants` (
  `id` int NOT NULL AUTO_INCREMENT,
  `assignment_id` int NOT NULL,
  `assistant_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bus_assignments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `bus_id` int NOT NULL,
  `driver_id` int NOT NULL,
  `route_id` int NOT NULL,
  `effective_date` date NOT NULL,
  `status` enum('active','inactive') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'active',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bus_attendance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `assignment_id` int NOT NULL,
  `date` date NOT NULL,
  `pickup_status` enum('present','absent') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'absent',
  `dropoff_status` enum('present','absent') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'absent',
  `stop_id` int NOT NULL,
  `recorded_by` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bus_maintenance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `bus_id` int NOT NULL,
  `maintenance_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `cost` decimal(10,2) DEFAULT '0.00',
  `maintenance_date` date NOT NULL,
  `next_maintenance_date` date DEFAULT NULL,
  `recorded_by` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bus_routes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_id` int NOT NULL,
  `route_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_time` time NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bus_stop_prices` (
  `id` int NOT NULL AUTO_INCREMENT,
  `route_id` int NOT NULL,
  `stop_id` int NOT NULL,
  `monthly_price` decimal(10,2) DEFAULT '0.00',
  `quarter_price` decimal(10,2) DEFAULT '0.00',
  `semester_price` decimal(10,2) DEFAULT '0.00',
  `oneyear_price` decimal(10,2) DEFAULT '0.00',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bus_stops` (
  `id` int NOT NULL AUTO_INCREMENT,
  `route_id` int NOT NULL,
  `stop_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `stop_order` int NOT NULL,
  `lat` decimal(10,7) DEFAULT NULL,
  `lng` decimal(10,7) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bus_stu_inroll` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `route_id` int NOT NULL,
  `stop_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `start_date` date DEFAULT NULL,
  `status` enum('active','inactive') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'active',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `buses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `plate_number` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `car_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `color` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `car_year` int NOT NULL,
  `capacity` int NOT NULL,
  `branch_id` int NOT NULL,
  `status` enum('active','inactive') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'active',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `category` (
  `id` int NOT NULL AUTO_INCREMENT,
  `category_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `certificate_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academic_id` int NOT NULL,
  `prefix` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `surfix` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `digit` int DEFAULT NULL,
  `year` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `orientation` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `check_in_security_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `user_id` int DEFAULT NULL,
  `client_ip` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_type` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `severity` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `detail_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `user_agent` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_check_in_security_events_id` (`id`) USING BTREE,
  KEY `ix_check_in_security_events_event_type` (`event_type`) USING BTREE,
  KEY `ix_check_in_security_events_client_ip` (`client_ip`) USING BTREE,
  KEY `ix_check_in_security_events_created_at` (`created_at`) USING BTREE,
  KEY `ix_check_in_security_events_severity` (`severity`) USING BTREE,
  KEY `ix_check_in_security_events_user_id` (`user_id`) USING BTREE,
  CONSTRAINT `check_in_security_events_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=1662 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `class_teachers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `teacher_id` int NOT NULL,
  `teacher_assistant_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `grade_type_id` int NOT NULL,
  `shift_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `noted` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `academic_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_class_teachers_teacher_academic` (`teacher_id`,`academic_id`) USING BTREE,
  KEY `idx_class_teachers_grade_shift` (`grade_id`,`shift_id`,`academic_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=250 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `classes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `class_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `credits` int DEFAULT NULL,
  `max_students` int DEFAULT NULL,
  `teacher_id` int NOT NULL,
  `semester` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `academic_year` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `ix_classes_class_code` (`class_code`) USING BTREE,
  KEY `ix_classes_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `daily_attendance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `grade_type_id` int NOT NULL,
  `shift_id` int NOT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `attendance_date` date NOT NULL,
  `academic_id` int DEFAULT NULL,
  `note` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `teacher_id` int NOT NULL,
  `created_by_type` enum('teacher','parent','student') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'teacher',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_attendance` (`student_id`,`program_id`,`grade_id`,`grade_type_id`,`shift_id`,`attendance_date`) USING BTREE,
  KEY `ix_daily_attendance_created_by_type` (`created_by_type`) USING BTREE,
  KEY `idx_attendance_student_date` (`student_id`,`attendance_date`) USING BTREE,
  KEY `idx_attendance_program_grade_shift` (`program_id`,`grade_id`,`shift_id`,`academic_id`) USING BTREE,
  KEY `idx_attendance_academic` (`academic_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=187158 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `decimal_marks_allow` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `program_id` int unsigned NOT NULL,
  `allow` decimal(3,2) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_program_allow` (`program_id`,`allow`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `demo_cert` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `cer_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cer_model` int DEFAULT NULL,
  `academic_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_type_id` int DEFAULT NULL,
  `grade_id` int NOT NULL,
  `nittes_id` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `snapshot_background_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `snapshot_signature_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `snapshot_stamp_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `snapshot_cert_date` date DEFAULT NULL,
  `snapshot_director_kname` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `snapshot_director_ename` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `snapshot_principal_label` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `snapshot_address_prefix` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `snapshot_date_format` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_public` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1396 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `department` (
  `id` int NOT NULL AUTO_INCREMENT,
  `department` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `translate` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `departments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `department` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `translate` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_departments_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `device_tokens` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL COMMENT 'User ID (parent, teacher, student, etc.)',
  `user_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'user_type: parent, teacher, student, staff',
  `device_token` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'FCM device token',
  `device_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'android, ios, web',
  `device_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Device name/model',
  `app_version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'App version',
  `is_active` tinyint(1) DEFAULT '1' COMMENT '1 = active, 0 = inactive',
  `last_used_at` timestamp NULL DEFAULT NULL COMMENT 'Last time token was used',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `notifications_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `attendance_notifications_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `leave_notifications_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `message_notifications_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `announcement_notifications_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `market_notifications_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `other_notifications_enabled` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_user_device` (`user_id`,`user_type`,`device_token`) USING BTREE,
  KEY `idx_user` (`user_id`,`user_type`) USING BTREE,
  KEY `idx_token` (`device_token`) USING BTREE,
  KEY `idx_active` (`is_active`,`last_used_at`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=55384 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `discount_childs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `discount_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `child_count` int NOT NULL,
  `amount` decimal(65,2) NOT NULL,
  `academic_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `discount_result` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `grade_scale_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `enrollments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `class_id` int NOT NULL,
  `enrollment_date` datetime DEFAULT CURRENT_TIMESTAMP,
  `grade` varchar(5) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_enrollments_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `exam_calculate_sign` (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_id` int NOT NULL,
  `grade_group_id` int DEFAULT NULL,
  `academic_id` int NOT NULL,
  `marks_system_id` int DEFAULT NULL,
  `result_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `formula_expression` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `sign_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `divide_by_multiplier` decimal(65,2) DEFAULT NULL,
  `exam_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=187 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `exam_calculate_sign_subjects` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_calculate_sign_id` int NOT NULL,
  `subject_id` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_sign_id` (`exam_calculate_sign_id`) USING BTREE,
  KEY `idx_subject_id` (`subject_id`) USING BTREE,
  CONSTRAINT `fk_sign_subjects_sign` FOREIGN KEY (`exam_calculate_sign_id`) REFERENCES `exam_calculate_sign` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=2430 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `expense_categories` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `is_active` tinyint(1) DEFAULT '1',
  `created_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `expenses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `expense_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ref` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `total_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `amount_tobepay` decimal(12,2) DEFAULT '0.00',
  `paid_amount` decimal(12,2) DEFAULT '0.00',
  `vat` decimal(5,2) DEFAULT '0.00',
  `discount` decimal(12,2) DEFAULT '0.00',
  `discount_type` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'amount',
  `remaining_amount` decimal(12,2) DEFAULT '0.00',
  `payment_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'Pending',
  `payment_method` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'Cash',
  `due_date` datetime DEFAULT NULL,
  `next_payment` datetime DEFAULT NULL,
  `exchange_rate` decimal(10,4) DEFAULT '1.0000',
  `note` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `academic_id` int DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `last_account_id` int DEFAULT NULL,
  `created_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `expense_no` (`expense_no`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `feature_locks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `feature_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `feature_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_locked` tinyint(1) NOT NULL,
  `locked_by` int DEFAULT NULL,
  `locked_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `locked_by` (`locked_by`) USING BTREE,
  KEY `ix_feature_locks_feature_id` (`feature_id`) USING BTREE,
  KEY `ix_feature_locks_is_locked` (`is_locked`) USING BTREE,
  CONSTRAINT `feature_locks_ibfk_1` FOREIGN KEY (`locked_by`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fee_services` (
  `id` int NOT NULL AUTO_INCREMENT,
  `service_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(65,2) NOT NULL,
  `branch_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `special` int DEFAULT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `feedbacks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `child_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `guardian_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `phone_number` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `grade_level` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `location` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `feedback` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=41 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `form_field_options` (
  `id` int NOT NULL AUTO_INCREMENT,
  `field_id` int NOT NULL,
  `label` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `order` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `field_id` (`field_id`) USING BTREE,
  KEY `ix_form_field_options_id` (`id`) USING BTREE,
  CONSTRAINT `form_field_options_ibfk_1` FOREIGN KEY (`field_id`) REFERENCES `form_fields` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=158 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `form_fields` (
  `id` int NOT NULL AUTO_INCREMENT,
  `form_id` int NOT NULL,
  `field_type` enum('short_text','long_text','number','dropdown','checkboxes','radio','date','time','child_selector','image','file') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `label` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `display_only` tinyint(1) NOT NULL,
  `is_required` tinyint(1) NOT NULL,
  `order` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `form_id` (`form_id`) USING BTREE,
  KEY `ix_form_fields_id` (`id`) USING BTREE,
  CONSTRAINT `form_fields_ibfk_1` FOREIGN KEY (`form_id`) REFERENCES `forms` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=62 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `form_submission_values` (
  `id` int NOT NULL AUTO_INCREMENT,
  `submission_id` int NOT NULL,
  `field_id` int NOT NULL,
  `value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `submission_id` (`submission_id`) USING BTREE,
  KEY `field_id` (`field_id`) USING BTREE,
  KEY `ix_form_submission_values_id` (`id`) USING BTREE,
  CONSTRAINT `form_submission_values_ibfk_1` FOREIGN KEY (`submission_id`) REFERENCES `form_submissions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `form_submission_values_ibfk_2` FOREIGN KEY (`field_id`) REFERENCES `form_fields` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=128 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `form_submissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `form_id` int NOT NULL,
  `user_id` int NOT NULL,
  `user_type` enum('all','parents','students','teachers') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `submitted_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `form_id` (`form_id`) USING BTREE,
  KEY `ix_form_submissions_id` (`id`) USING BTREE,
  CONSTRAINT `form_submissions_ibfk_1` FOREIGN KEY (`form_id`) REFERENCES `forms` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=128 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `forms` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `target_role` enum('all','parents','students','teachers') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `allow_multiple_submissions` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `start_date` datetime DEFAULT NULL,
  `end_date` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_forms_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `grade` (
  `id` int NOT NULL AUTO_INCREMENT,
  `grade_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `grade_name_us` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `grade_type_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `group_Id` int NOT NULL,
  `program_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_by` int NOT NULL,
  `created_by` int NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=192 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `grade_group` (
  `id` int NOT NULL AUTO_INCREMENT,
  `group_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `academic_id` int NOT NULL,
  `program_id` int NOT NULL,
  `multiplier` decimal(10,2) NOT NULL,
  `model_cer` int DEFAULT '1',
  `noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_by` int NOT NULL,
  `created_by` int NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `grade_scale` (
  `id` int NOT NULL AUTO_INCREMENT,
  `grade_group_id` int NOT NULL,
  `academic_id` int NOT NULL DEFAULT '1',
  `min_marks` decimal(65,2) NOT NULL,
  `max_marks` decimal(65,2) NOT NULL,
  `us_grade` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `nittes_id` int DEFAULT NULL,
  `scale_discount` decimal(10,2) DEFAULT '0.00',
  `kh_grade` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_overall` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=130 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `grade_type` (
  `id` int NOT NULL AUTO_INCREMENT,
  `type_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `program_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `shift_id` int DEFAULT NULL,
  `noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=127 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `holidays` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `date` date NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=113 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `hot_event_impressions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `hot_event_id` int NOT NULL,
  `user_id` int NOT NULL,
  `impression_count` int NOT NULL,
  `last_viewed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_hot_event_impressions_user_id` (`user_id`) USING BTREE,
  KEY `ix_hot_event_impressions_hot_event_id` (`hot_event_id`) USING BTREE,
  KEY `ix_hot_event_impressions_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=626 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `hot_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_at` datetime DEFAULT NULL,
  `end_at` datetime NOT NULL,
  `audience` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `frequency` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `interval_minutes` int DEFAULT NULL,
  `max_impressions` int DEFAULT NULL,
  `link_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status_text` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_hot_events_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `inventories` (
  `id` int NOT NULL AUTO_INCREMENT,
  `product_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `unit_id` int NOT NULL,
  `sell_amount` decimal(65,2) NOT NULL,
  `buy_amount` decimal(65,2) NOT NULL,
  `currency` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `exchange_rate` decimal(65,2) DEFAULT NULL,
  `accounts_id` int NOT NULL,
  `category_id` int NOT NULL,
  `qty` int NOT NULL,
  `note` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `branch_id` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=56 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `invoice` (
  `id` int NOT NULL AUTO_INCREMENT,
  `invoice_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `ref` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `student_id` int NOT NULL,
  `total_amount` decimal(10,2) NOT NULL,
  `amount_noDiscount` decimal(65,2) DEFAULT NULL,
  `amount_tobepay` decimal(65,2) DEFAULT NULL,
  `paid_amount` decimal(10,2) NOT NULL,
  `vat` decimal(65,2) DEFAULT NULL,
  `discount` decimal(10,2) NOT NULL,
  `discount_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `remaining_amount` decimal(10,2) NOT NULL,
  `payment_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `due_date` date NOT NULL,
  `pay_from` date DEFAULT NULL,
  `no_past` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `exchange_rate` decimal(10,2) NOT NULL,
  `next_payment` date DEFAULT NULL,
  `payment_method` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `note` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `academic_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `academic_finnish` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `isDone` tinyint(1) NOT NULL DEFAULT '0',
  `created_invoice_at` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` int NOT NULL,
  `payer` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `programList` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pay_term` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `last_account_id` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=294 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `invoice_items` (
  `id` int NOT NULL AUTO_INCREMENT,
  `invoice_id` int DEFAULT NULL,
  `ref` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `itemId` int DEFAULT NULL,
  `table_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `grade_id` int DEFAULT NULL,
  `grade_type_id` int DEFAULT NULL,
  `shift_id` int DEFAULT NULL,
  `items_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `item_price` decimal(65,2) DEFAULT NULL,
  `item_qty` int DEFAULT NULL,
  `unit` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `discount` decimal(65,2) DEFAULT NULL,
  `discount_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `total_price` decimal(65,2) DEFAULT NULL,
  `academic_id` int DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `isNext` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'false',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1475 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `items_group` (
  `id` int NOT NULL AUTO_INCREMENT,
  `group_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `items_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `unit_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `learning` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academicid` int NOT NULL,
  `studentid` int NOT NULL,
  `branch_id` int DEFAULT NULL,
  `programid` int NOT NULL,
  `gradeid` int NOT NULL,
  `grade_type_id` int NOT NULL DEFAULT '1',
  `shiftid` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_learning_student_academic` (`studentid`,`academicid`) USING BTREE,
  KEY `idx_learning_grade_shift` (`gradeid`,`shiftid`) USING BTREE,
  KEY `idx_learning_program` (`programid`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3466 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `learning_class_schedules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academic_id` int NOT NULL,
  `branch_id` int NOT NULL COMMENT 'Links to branch table',
  `program_id` int NOT NULL,
  `grade_group_id` int NOT NULL COMMENT 'Links to grade_group table',
  `grade_id` int DEFAULT NULL COMMENT 'Links to grade table',
  `grade_type_id` int DEFAULT NULL COMMENT 'Specific single grade type ID for this schedule',
  `shift_id` int DEFAULT NULL,
  `subject_id` int NOT NULL COMMENT 'Links to subjects table',
  `teacher_id` int NOT NULL COMMENT 'Links to teachers/users table',
  `time_slot_id` int NOT NULL,
  `day_of_week` smallint NOT NULL COMMENT '1=Monday, 7=Sunday',
  `room_number` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_learning_class_schedules_teacher_id` (`teacher_id`) USING BTREE,
  KEY `ix_learning_class_schedules_grade_group_id` (`grade_group_id`) USING BTREE,
  KEY `ix_learning_class_schedules_academic_id` (`academic_id`) USING BTREE,
  KEY `ix_learning_class_schedules_branch_id` (`branch_id`) USING BTREE,
  KEY `ix_learning_class_schedules_grade_id` (`grade_id`) USING BTREE,
  KEY `ix_learning_class_schedules_subject_id` (`subject_id`) USING BTREE,
  KEY `ix_learning_class_schedules_id` (`id`) USING BTREE,
  KEY `ix_learning_class_schedule_shift` (`shift_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1998 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `learning_homework` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academic_id` int NOT NULL,
  `class_schedule_id` int DEFAULT NULL,
  `branch_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_group_id` int NOT NULL,
  `grade_id` int DEFAULT NULL,
  `grade_type_id` int DEFAULT NULL,
  `shift_id` int NOT NULL,
  `subject_id` int NOT NULL,
  `teacher_id` int NOT NULL,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `homework_date` date NOT NULL,
  `due_date` date DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_learning_homework_academic` (`academic_id`) USING BTREE,
  KEY `ix_learning_homework_schedule` (`class_schedule_id`) USING BTREE,
  KEY `ix_learning_homework_teacher` (`teacher_id`) USING BTREE,
  KEY `ix_learning_homework_class` (`academic_id`,`program_id`,`grade_id`,`shift_id`) USING BTREE,
  KEY `ix_learning_homework_created` (`created_at`) USING BTREE,
  KEY `ix_learning_homework_date` (`homework_date`) USING BTREE,
  KEY `fk_learning_homework_subject` (`subject_id`) USING BTREE,
  CONSTRAINT `fk_learning_homework_schedule` FOREIGN KEY (`class_schedule_id`) REFERENCES `learning_class_schedules` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `fk_learning_homework_subject` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_learning_homework_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `learning_homework_attachments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `homework_id` int NOT NULL,
  `file_url` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_type` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_size` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_learning_homework_attachment_homework` (`homework_id`) USING BTREE,
  CONSTRAINT `fk_learning_homework_attachment_homework` FOREIGN KEY (`homework_id`) REFERENCES `learning_homework` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `learning_schedule_exceptions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `class_schedule_id` int NOT NULL,
  `exception_date` date NOT NULL,
  `exception_type` enum('cancelled','rescheduled','room_change','teacher_change') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `new_time_slot_id` int DEFAULT NULL,
  `new_room_number` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `substitute_teacher_id` int DEFAULT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_learning_schedule_exceptions_exception_date` (`exception_date`) USING BTREE,
  KEY `ix_learning_schedule_exceptions_id` (`id`) USING BTREE,
  KEY `ix_learning_schedule_exceptions_class_schedule_id` (`class_schedule_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `learning_session_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `class_schedule_id` int NOT NULL,
  `session_date` date NOT NULL,
  `teacher_id` int NOT NULL,
  `start_time` time DEFAULT NULL,
  `end_time` time DEFAULT NULL,
  `topic_covered` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `homework_assigned` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `attendance_count` int DEFAULT NULL,
  `status` enum('scheduled','completed','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `cancellation_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_learning_session_logs_id` (`id`) USING BTREE,
  KEY `ix_learning_session_logs_class_schedule_id` (`class_schedule_id`) USING BTREE,
  KEY `ix_learning_session_logs_session_date` (`session_date`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `learning_time_slot_scopes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `time_slot_id` int NOT NULL,
  `scope_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope_id` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `shift_id` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_learning_time_slot_scopes_id` (`id`) USING BTREE,
  KEY `ix_learning_time_slot_scopes_time_slot_id` (`time_slot_id`) USING BTREE,
  CONSTRAINT `learning_time_slot_scopes_ibfk_1` FOREIGN KEY (`time_slot_id`) REFERENCES `learning_time_slots` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=411 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `learning_time_slots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `slot_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `duration_minutes` int DEFAULT NULL,
  `sort_order` int DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `is_global` tinyint(1) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `grade_group_id` int DEFAULT NULL,
  `grade_id` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_learning_time_slots_id` (`id`) USING BTREE,
  KEY `ix_learning_time_slots_grade_group_id` (`grade_group_id`) USING BTREE,
  KEY `ix_learning_time_slots_grade_id` (`grade_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=49 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_approvers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `department_id` int DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `can_approve_all` tinyint(1) DEFAULT NULL,
  `max_days_can_approve` float DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `can_create_for_staff` tinyint(1) DEFAULT NULL,
  `can_adjust_leave_balance` tinyint(1) DEFAULT NULL,
  `can_view_all_requests` tinyint(1) DEFAULT NULL,
  `can_cancel_approved_leave` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `user_id` (`user_id`) USING BTREE,
  KEY `ix_leave_approvers_id` (`id`) USING BTREE,
  CONSTRAINT `leave_approvers_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_balance_adjustments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `leave_type_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `amount_days` float NOT NULL,
  `effective_date` date NOT NULL,
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` int NOT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `voided_by` int DEFAULT NULL,
  `void_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `voided_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `created_by` (`created_by`) USING BTREE,
  KEY `voided_by` (`voided_by`) USING BTREE,
  KEY `ix_leave_balance_adjustments_status` (`status`) USING BTREE,
  KEY `ix_leave_balance_adjustments_leave_type_id` (`leave_type_id`) USING BTREE,
  KEY `ix_leave_balance_adjustments_effective_date` (`effective_date`) USING BTREE,
  KEY `ix_leave_balance_adjustments_id` (`id`) USING BTREE,
  KEY `ix_leave_balance_adjustments_academic_id` (`academic_id`) USING BTREE,
  KEY `ix_leave_balance_adjustments_user_id` (`user_id`) USING BTREE,
  CONSTRAINT `leave_balance_adjustments_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_balance_adjustments_ibfk_2` FOREIGN KEY (`leave_type_id`) REFERENCES `leave_types` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_balance_adjustments_ibfk_3` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_balance_adjustments_ibfk_4` FOREIGN KEY (`voided_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_balances` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `leave_type_id` int NOT NULL,
  `policy_id` int DEFAULT NULL,
  `accrued_days` float DEFAULT NULL,
  `taken_days` float DEFAULT NULL,
  `remaining_days` float DEFAULT NULL,
  `carry_forward_days` float DEFAULT NULL,
  `last_accrual_date` date DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_leave_balances_id` (`id`) USING BTREE,
  KEY `idx_leave_balances_user_id` (`user_id`) USING BTREE,
  KEY `idx_leave_balances_leave_type_id` (`leave_type_id`) USING BTREE,
  KEY `idx_leave_balances_policy_id` (`policy_id`) USING BTREE,
  CONSTRAINT `leave_balances_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_balances_ibfk_2` FOREIGN KEY (`leave_type_id`) REFERENCES `leave_types` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_balances_ibfk_3` FOREIGN KEY (`policy_id`) REFERENCES `leave_policies` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_histories` (
  `id` int NOT NULL AUTO_INCREMENT,
  `leave_request_id` int NOT NULL,
  `action` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `old_status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `new_status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_by` int NOT NULL,
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `leave_request_id` (`leave_request_id`) USING BTREE,
  KEY `changed_by` (`changed_by`) USING BTREE,
  KEY `ix_leave_histories_id` (`id`) USING BTREE,
  CONSTRAINT `leave_histories_ibfk_1` FOREIGN KEY (`leave_request_id`) REFERENCES `leave_requests` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_histories_ibfk_2` FOREIGN KEY (`changed_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=276 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_policies` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `department_id` int DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_leave_policies_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_policy_leave_type_association` (
  `leave_policy_id` int NOT NULL,
  `leave_type_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`leave_policy_id`,`leave_type_id`) USING BTREE,
  KEY `leave_type_id` (`leave_type_id`) USING BTREE,
  CONSTRAINT `leave_policy_leave_type_association_ibfk_1` FOREIGN KEY (`leave_policy_id`) REFERENCES `leave_policies` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_policy_leave_type_association_ibfk_2` FOREIGN KEY (`leave_type_id`) REFERENCES `leave_types` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_request_days` (
  `id` int NOT NULL AUTO_INCREMENT,
  `leave_request_id` int NOT NULL,
  `leave_date` date NOT NULL,
  `scope` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_indexes` json DEFAULT NULL,
  `sessions_total` int DEFAULT NULL,
  `day_cost` float NOT NULL,
  `time_from` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `time_to` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `paid_cost` float DEFAULT NULL,
  `unpaid_cost` float DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_leave_request_days_leave_request_id` (`leave_request_id`) USING BTREE,
  KEY `ix_leave_request_days_leave_date` (`leave_date`) USING BTREE,
  KEY `ix_leave_request_days_id` (`id`) USING BTREE,
  CONSTRAINT `leave_request_days_ibfk_1` FOREIGN KEY (`leave_request_id`) REFERENCES `leave_requests` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=222 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `leave_type_id` int NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `approver_id` int DEFAULT NULL,
  `approval_date` datetime DEFAULT NULL,
  `rejection_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `academic_id` int DEFAULT NULL,
  `total_days` float DEFAULT NULL,
  `replacement_user_id` int DEFAULT NULL,
  `proof_image_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `replacement_note` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `cancelled_by` int DEFAULT NULL,
  `cancelled_at` datetime DEFAULT NULL,
  `cancel_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_by` int DEFAULT NULL,
  `creation_source` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `review_reminder_count` int NOT NULL,
  `last_review_reminder_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `user_id` (`user_id`) USING BTREE,
  KEY `leave_type_id` (`leave_type_id`) USING BTREE,
  KEY `approver_id` (`approver_id`) USING BTREE,
  KEY `ix_leave_requests_id` (`id`) USING BTREE,
  CONSTRAINT `leave_requests_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_requests_ibfk_2` FOREIGN KEY (`leave_type_id`) REFERENCES `leave_types` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_requests_ibfk_3` FOREIGN KEY (`approver_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=135 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_type_allocations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `leave_type_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `allocated_days` float NOT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_leave_alloc_type_academic` (`leave_type_id`,`academic_id`) USING BTREE,
  KEY `ix_leave_type_allocations_leave_type_id` (`leave_type_id`) USING BTREE,
  KEY `ix_leave_type_allocations_academic_id` (`academic_id`) USING BTREE,
  KEY `ix_leave_type_allocations_id` (`id`) USING BTREE,
  CONSTRAINT `leave_type_allocations_ibfk_1` FOREIGN KEY (`leave_type_id`) REFERENCES `leave_types` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_types` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `max_days_per_year` float NOT NULL,
  `is_paid` tinyint(1) DEFAULT NULL,
  `requires_approval` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `requires_proof` tinyint(1) DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `display_order` int DEFAULT NULL,
  `color_hex` varchar(7) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `max_days_per_month` float DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_leave_types_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `login_attempts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `computer_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `computer_user_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `computer_unique_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `mac_address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `motherboard_serial` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `processor_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `windows_product_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `operating_system` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `user_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_success` tinyint(1) NOT NULL,
  `failure_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `login_time` datetime NOT NULL,
  `ip_address` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `app_version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `edition` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_username` (`username`) USING BTREE,
  KEY `idx_login_time` (`login_time`) USING BTREE,
  KEY `idx_computer_unique_id` (`computer_unique_id`) USING BTREE,
  KEY `idx_computer_user_name` (`computer_user_name`) USING BTREE,
  KEY `idx_motherboard_serial` (`motherboard_serial`) USING BTREE,
  KEY `idx_processor_id` (`processor_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3142 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `logtransaction` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ref` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `accounts_id` int NOT NULL,
  `transaction_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(65,2) NOT NULL,
  `currency` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `exchange_rate` decimal(65,2) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=338 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `mark_entry_locks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `grade_type_id` int DEFAULT NULL,
  `academic_id` int NOT NULL,
  `marks_system_id` int NOT NULL,
  `subject_id` int NOT NULL,
  `locked_by` int NOT NULL,
  `locked_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `unlocked_at` datetime DEFAULT NULL,
  `unlocked_by` int DEFAULT NULL,
  `is_locked` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_mark_entry_locks_context` (`program_id`,`grade_id`,`grade_type_id`,`academic_id`,`marks_system_id`,`subject_id`) USING BTREE,
  KEY `idx_mark_entry_locks_locked_by` (`locked_by`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=112 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `mark_lock_attempts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `failed_attempts` int NOT NULL DEFAULT '0',
  `penalty_level` int NOT NULL DEFAULT '0',
  `locked_until` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `user_id` (`user_id`) USING BTREE,
  KEY `idx_mark_lock_attempts_user` (`user_id`) USING BTREE,
  KEY `idx_mark_lock_attempts_locked_until` (`locked_until`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `mark_lock_passcodes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `passcode_hash` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `user_id` (`user_id`) USING BTREE,
  KEY `idx_mark_lock_passcodes_user` (`user_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_categories` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_en` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_km` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `icon_key` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sort_order` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `name` (`name`) USING BTREE,
  KEY `ix_market_categories_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_listing_broadcasts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `store_id` int NOT NULL,
  `listing_id` int NOT NULL,
  `publication_at` datetime NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_market_listing_broadcasts_listing_id` (`listing_id`) USING BTREE,
  KEY `ix_market_listing_broadcasts_id` (`id`) USING BTREE,
  KEY `ix_market_listing_broadcasts_store_id` (`store_id`) USING BTREE,
  KEY `ix_market_broadcast_listing_created` (`listing_id`,`created_at`) USING BTREE,
  KEY `ix_market_broadcast_store_created` (`store_id`,`created_at`) USING BTREE,
  CONSTRAINT `market_listing_broadcasts_ibfk_1` FOREIGN KEY (`store_id`) REFERENCES `market_stores` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `market_listing_broadcasts_ibfk_2` FOREIGN KEY (`listing_id`) REFERENCES `market_listings` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_listing_images` (
  `id` int NOT NULL AUTO_INCREMENT,
  `listing_id` int NOT NULL,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_market_listing_images_id` (`id`) USING BTREE,
  KEY `ix_market_listing_images_listing_id` (`listing_id`) USING BTREE,
  CONSTRAINT `market_listing_images_ibfk_1` FOREIGN KEY (`listing_id`) REFERENCES `market_listings` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_listings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `store_id` int NOT NULL,
  `category_id` int DEFAULT NULL,
  `title` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `price` decimal(12,2) NOT NULL,
  `compare_at_price` decimal(12,2) DEFAULT NULL,
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `stock_qty` int DEFAULT NULL,
  `view_count` int NOT NULL,
  `condition` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_featured` tinyint(1) DEFAULT '0',
  `featured_until` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  `renewed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_market_listings_store_id` (`store_id`) USING BTREE,
  KEY `ix_market_listings_category_id` (`category_id`) USING BTREE,
  KEY `ix_market_listings_id` (`id`) USING BTREE,
  KEY `ix_market_listings_status_created` (`status`,`created_at`) USING BTREE,
  KEY `ix_market_listings_status` (`status`) USING BTREE,
  CONSTRAINT `market_listings_ibfk_1` FOREIGN KEY (`store_id`) REFERENCES `market_stores` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `market_listings_ibfk_2` FOREIGN KEY (`category_id`) REFERENCES `market_categories` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_orders` (
  `id` int NOT NULL AUTO_INCREMENT,
  `listing_id` int NOT NULL,
  `store_id` int NOT NULL,
  `buyer_user_id` int NOT NULL,
  `buyer_user_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `seller_user_id` int NOT NULL,
  `seller_user_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `quantity` int NOT NULL,
  `buyer_note` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `seller_note` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_market_orders_store_id` (`store_id`) USING BTREE,
  KEY `ix_market_orders_buyer` (`buyer_user_id`,`buyer_user_type`) USING BTREE,
  KEY `ix_market_orders_listing_id` (`listing_id`) USING BTREE,
  KEY `ix_market_orders_status` (`status`) USING BTREE,
  KEY `ix_market_orders_seller` (`seller_user_id`,`seller_user_type`) USING BTREE,
  KEY `ix_market_orders_id` (`id`) USING BTREE,
  CONSTRAINT `market_orders_ibfk_1` FOREIGN KEY (`listing_id`) REFERENCES `market_listings` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `market_orders_ibfk_2` FOREIGN KEY (`store_id`) REFERENCES `market_stores` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_reviews` (
  `id` int NOT NULL AUTO_INCREMENT,
  `listing_id` int NOT NULL,
  `store_id` int NOT NULL,
  `reviewer_user_id` int NOT NULL,
  `reviewer_user_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `rating` int NOT NULL,
  `comment` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `order_id` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_market_review_once` (`listing_id`,`reviewer_user_id`,`reviewer_user_type`) USING BTREE,
  KEY `order_id` (`order_id`) USING BTREE,
  KEY `ix_market_reviews_store_id` (`store_id`) USING BTREE,
  KEY `ix_market_reviews_id` (`id`) USING BTREE,
  KEY `ix_market_reviews_listing` (`listing_id`) USING BTREE,
  KEY `ix_market_reviews_store` (`store_id`) USING BTREE,
  KEY `ix_market_reviews_listing_id` (`listing_id`) USING BTREE,
  CONSTRAINT `market_reviews_ibfk_1` FOREIGN KEY (`listing_id`) REFERENCES `market_listings` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `market_reviews_ibfk_2` FOREIGN KEY (`store_id`) REFERENCES `market_stores` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `market_reviews_ibfk_3` FOREIGN KEY (`order_id`) REFERENCES `market_orders` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_seller_bans` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `user_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `banned_until` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_market_seller_bans_user_type` (`user_type`) USING BTREE,
  KEY `ix_market_seller_bans_id` (`id`) USING BTREE,
  KEY `ix_market_seller_bans_user_id` (`user_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_settings` (
  `id` int NOT NULL,
  `welcome_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `welcome_skip_seconds` int NOT NULL DEFAULT '30',
  `welcome_version` int NOT NULL DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_stores` (
  `id` int NOT NULL AUTO_INCREMENT,
  `seller_user_id` int NOT NULL,
  `seller_user_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `tagline` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `contact_email` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `contact_phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `contact_telegram` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `logo_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cover_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  `name_changed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_market_store_seller` (`seller_user_id`,`seller_user_type`) USING BTREE,
  KEY `ix_market_stores_id` (`id`) USING BTREE,
  KEY `ix_market_stores_seller_user_id` (`seller_user_id`) USING BTREE,
  KEY `ix_market_stores_seller_user_type` (`seller_user_type`) USING BTREE,
  KEY `ix_market_stores_status` (`status`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=43 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `market_wishlists` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `user_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `listing_id` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_market_wishlist_once` (`user_id`,`user_type`,`listing_id`) USING BTREE,
  KEY `ix_market_wishlists_listing_id` (`listing_id`) USING BTREE,
  KEY `ix_market_wishlists_user` (`user_id`,`user_type`) USING BTREE,
  KEY `ix_market_wishlists_id` (`id`) USING BTREE,
  CONSTRAINT `market_wishlists_ibfk_1` FOREIGN KEY (`listing_id`) REFERENCES `market_listings` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `marks_input` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `grade_group_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `subject_id` int NOT NULL,
  `marks_system_id` int DEFAULT NULL,
  `marks` decimal(65,2) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uniq_marks_input_entry` (`student_id`,`academic_id`,`program_id`,`grade_id`,`subject_id`,`marks_system_id`) USING BTREE,
  KEY `idx_marks_input_student_academic` (`student_id`,`academic_id`) USING BTREE,
  KEY `idx_marks_input_marks_system` (`marks_system_id`,`student_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=78729 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `marks_monthly` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_name` varchar(25) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `student_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `grade_group_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `marks_input_ids` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `marks_system_id` int NOT NULL,
  `total` decimal(65,2) DEFAULT NULL,
  `average` decimal(65,2) DEFAULT NULL,
  `grade_scale_id` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `teacher_comment` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `director_comment` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=8808 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `marks_monthly_items` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `marks_monthly_id` int NOT NULL,
  `marks_input_id` bigint NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_monthly_input` (`marks_monthly_id`,`marks_input_id`) USING BTREE,
  KEY `idx_marks_monthly_id` (`marks_monthly_id`) USING BTREE,
  KEY `idx_marks_input_id` (`marks_input_id`) USING BTREE,
  CONSTRAINT `fk_marks_monthly_items_monthly` FOREIGN KEY (`marks_monthly_id`) REFERENCES `marks_monthly` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=425384 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `marks_semester` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_name` varchar(25) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `student_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `grade_group_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `marks_imonthly_ids` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `marks_system_id` int NOT NULL,
  `total` decimal(10,2) DEFAULT '0.00',
  `average` decimal(10,2) DEFAULT '0.00',
  `grade_scale_id` int DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `teacher_comment` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `director_comment` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_student_id` (`student_id`) USING BTREE,
  KEY `idx_program_id` (`program_id`) USING BTREE,
  KEY `idx_grade_id` (`grade_id`) USING BTREE,
  KEY `idx_grade_group_id` (`grade_group_id`) USING BTREE,
  KEY `idx_academic_id` (`academic_id`) USING BTREE,
  KEY `idx_marks_system_id` (`marks_system_id`) USING BTREE,
  KEY `idx_grade_scale_id` (`grade_scale_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=2416 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `marks_semester_monthlies` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `marks_semester_id` int NOT NULL,
  `marks_monthly_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_semester_monthly` (`marks_semester_id`,`marks_monthly_id`) USING BTREE,
  KEY `idx_semester_id` (`marks_semester_id`) USING BTREE,
  KEY `idx_monthly_id` (`marks_monthly_id`) USING BTREE,
  CONSTRAINT `fk_semester_monthlies_semester` FOREIGN KEY (`marks_semester_id`) REFERENCES `marks_semester` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=456982 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `marks_system` (
  `id` int NOT NULL AUTO_INCREMENT,
  `marks_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `marks_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `subjects_ids` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `grade_group_id` int NOT NULL,
  `program_id` int NOT NULL,
  `for_month` date DEFAULT NULL,
  `academic_id` int NOT NULL,
  `created_by` int DEFAULT NULL,
  `updated_by` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `status` tinyint NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_marks_system_code` (`program_id`,`academic_id`,`grade_group_id`,`marks_code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=145 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `marks_system_subjects` (
  `id` int NOT NULL AUTO_INCREMENT,
  `marks_system_id` int NOT NULL,
  `subject_id` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_system_subject` (`marks_system_id`,`subject_id`) USING BTREE,
  KEY `idx_marks_system_id` (`marks_system_id`) USING BTREE,
  KEY `idx_subject_id` (`subject_id`) USING BTREE,
  CONSTRAINT `fk_system_subjects_system` FOREIGN KEY (`marks_system_id`) REFERENCES `marks_system` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=3666 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `marks_yearly` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_name` varchar(25) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `student_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `grade_group_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `marks_isemester_ids` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `marks_system_id` int NOT NULL,
  `total` decimal(10,2) DEFAULT '0.00',
  `average` decimal(10,2) DEFAULT '0.00',
  `grade_scale_id` int DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `teacher_comment` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `director_comment` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_student_id` (`student_id`) USING BTREE,
  KEY `idx_program_id` (`program_id`) USING BTREE,
  KEY `idx_grade_id` (`grade_id`) USING BTREE,
  KEY `idx_grade_group_id` (`grade_group_id`) USING BTREE,
  KEY `idx_academic_id` (`academic_id`) USING BTREE,
  KEY `idx_marks_system_id` (`marks_system_id`) USING BTREE,
  KEY `idx_grade_scale_id` (`grade_scale_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=805 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `marks_yearly_semesters` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `marks_yearly_id` int NOT NULL,
  `marks_semester_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_yearly_semester` (`marks_yearly_id`,`marks_semester_id`) USING BTREE,
  KEY `idx_yearly_id` (`marks_yearly_id`) USING BTREE,
  KEY `idx_semester_id` (`marks_semester_id`) USING BTREE,
  CONSTRAINT `fk_yearly_semesters_yearly` FOREIGN KEY (`marks_yearly_id`) REFERENCES `marks_yearly` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=1601 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `medal_points_setup` (
  `program_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `gold_pts` double DEFAULT '0',
  `silver_pts` double DEFAULT '0',
  `bronze_pts` double DEFAULT '0',
  `diamond_pts` double DEFAULT '0',
  `participation_pts` double DEFAULT '0',
  PRIMARY KEY (`program_name`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `medal_price` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name_us` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_kh` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(65,2) NOT NULL,
  `academic_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `medalname` (
  `id` int NOT NULL AUTO_INCREMENT,
  `medal_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=115 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `medals` (
  `id` int NOT NULL AUTO_INCREMENT,
  `cer_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `student_id` int NOT NULL,
  `medal_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `medal_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `medal_price_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `created_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT '2025-08-08 08:14:08',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=2281 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `message_group_bans` (
  `id` int NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `user_id` int NOT NULL,
  `user_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `banned_by` int NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `banned_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` datetime DEFAULT NULL,
  `is_active` int NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_message_group_bans_id` (`id`) USING BTREE,
  KEY `ix_message_group_bans_group_id` (`group_id`) USING BTREE,
  KEY `ix_message_group_bans_user_id` (`user_id`) USING BTREE,
  CONSTRAINT `message_group_bans_ibfk_1` FOREIGN KEY (`group_id`) REFERENCES `message_groups` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `message_group_members` (
  `id` int NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `user_id` int NOT NULL,
  `user_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `joined_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_message_group_members_id` (`id`) USING BTREE,
  KEY `ix_message_group_members_group_id` (`group_id`) USING BTREE,
  KEY `ix_message_group_members_user_id` (`user_id`) USING BTREE,
  CONSTRAINT `message_group_members_ibfk_1` FOREIGN KEY (`group_id`) REFERENCES `message_groups` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=2735 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `message_group_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `can_send_text` int NOT NULL DEFAULT '1',
  `can_send_files` int NOT NULL DEFAULT '1',
  `can_send_images` int NOT NULL DEFAULT '1',
  `can_send_voice` int NOT NULL DEFAULT '1',
  `only_admins_can_post` int NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `group_id` (`group_id`) USING BTREE,
  KEY `ix_message_group_settings_id` (`id`) USING BTREE,
  CONSTRAINT `message_group_settings_ibfk_1` FOREIGN KEY (`group_id`) REFERENCES `message_groups` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=81 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `message_groups` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `academic_year_id` int DEFAULT NULL,
  `grade_id` int DEFAULT NULL,
  `grade_type_id` int DEFAULT NULL,
  `program_id` int DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  `group_image` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_message_groups_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=97 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `message_pinned` (
  `id` int NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `message_id` int NOT NULL,
  `pinned_by` int NOT NULL,
  `pinned_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `message_id` (`message_id`) USING BTREE,
  KEY `ix_message_pinned_group_id` (`group_id`) USING BTREE,
  KEY `ix_message_pinned_id` (`id`) USING BTREE,
  CONSTRAINT `message_pinned_ibfk_1` FOREIGN KEY (`group_id`) REFERENCES `message_groups` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `message_pinned_ibfk_2` FOREIGN KEY (`message_id`) REFERENCES `messages` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `message_reactions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `message_id` int NOT NULL,
  `user_id` int NOT NULL,
  `reaction` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `user_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_message_reactions_message_id` (`message_id`) USING BTREE,
  KEY `ix_message_reactions_id` (`id`) USING BTREE,
  CONSTRAINT `message_reactions_ibfk_1` FOREIGN KEY (`message_id`) REFERENCES `messages` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `messages` (
  `id` int NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `sender_id` int NOT NULL,
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `message_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `read_by` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `deleted_by` int DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `is_hidden` int NOT NULL DEFAULT '0',
  `pinned_by` int DEFAULT NULL,
  `pinned_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_messages_sender_id` (`sender_id`) USING BTREE,
  KEY `ix_messages_created_at` (`created_at`) USING BTREE,
  KEY `ix_messages_id` (`id`) USING BTREE,
  KEY `ix_messages_group_id` (`group_id`) USING BTREE,
  CONSTRAINT `messages_ibfk_1` FOREIGN KEY (`group_id`) REFERENCES `message_groups` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=130 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `news` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `category` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `summary` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `cover_image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `target_audience` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'all' COMMENT 'Target audience: all, teachers, students, parents, admins…',
  `published_at` datetime DEFAULT NULL,
  `is_published` tinyint(1) NOT NULL,
  `author_id` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  `media_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `video_source` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `video_url` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `video_original_url` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `video_thumbnail_url` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `video_duration_seconds` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_news_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `news_images` (
  `id` int NOT NULL AUTO_INCREMENT,
  `news_id` int NOT NULL,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `caption` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `position` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_news_images_news_id` (`news_id`) USING BTREE,
  KEY `ix_news_images_id` (`id`) USING BTREE,
  CONSTRAINT `news_images_ibfk_1` FOREIGN KEY (`news_id`) REFERENCES `news` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=1560 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `nittes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name_us` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_kh` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `nittes_discount` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academic_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `amount` decimal(65,2) NOT NULL,
  `nittes_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `notifications` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int DEFAULT NULL,
  `user_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `body` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `is_read` tinyint(1) DEFAULT '0',
  `is_deletable` tinyint(1) DEFAULT '1',
  `redirect_route` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `redirect_args` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_notif_user` (`user_id`,`user_type`) USING BTREE,
  KEY `idx_notif_read` (`is_read`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=47886 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `otp_codes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `otp_hash` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `expiry` datetime NOT NULL,
  `attempts` int NOT NULL DEFAULT '0',
  `locked_until` datetime DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_username` (`username`) USING BTREE,
  KEY `idx_otp_expiry` (`expiry`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `parent_permission_interactions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `parent_id` int NOT NULL,
  `student_id` int NOT NULL,
  `learning_id` int NOT NULL,
  `interaction_date` date NOT NULL,
  `interaction_type` enum('requested','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_permission_parent_date` (`parent_id`,`interaction_date`) USING BTREE,
  KEY `ix_permission_student_learning` (`student_id`,`learning_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=131 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `parent_registration_audit` (
  `id` int NOT NULL AUTO_INCREMENT,
  `parent_id` int NOT NULL,
  `action` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `admin_user_id` int DEFAULT NULL,
  `admin_display` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `parent_snapshot` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `students_count` int NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_pra_action` (`action`) USING BTREE,
  KEY `idx_pra_created` (`created_at`) USING BTREE,
  KEY `idx_pra_parent` (`parent_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `parent_student_link_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `parent_id` int NOT NULL,
  `student_id` int NOT NULL,
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `parent_id` (`parent_id`) USING BTREE,
  KEY `student_id` (`student_id`) USING BTREE,
  CONSTRAINT `parent_student_link_requests_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `parents` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `parent_student_link_requests_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `parents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `uniqueid` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fatherName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `motherName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `fatherPhone` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `motherPhone` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fatherJob` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `motherJob` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pProvince` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pDistrict` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pCommune` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pVillage` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pEmail` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pTelegramId` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT '5591794523',
  `gName` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gPhone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gIsThe` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gHome` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gStreet` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gGroup` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gProvince` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gDistrict` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gCommune` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gVillage` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `myChilds` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` date NOT NULL,
  `updated_at` date NOT NULL,
  `status` int NOT NULL DEFAULT '1',
  `token_version` int DEFAULT '1',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_parents_status` (`status`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1016 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `partner_images` (
  `id` int NOT NULL AUTO_INCREMENT,
  `partner_id` int NOT NULL,
  `image_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_partner_images_id` (`id`) USING BTREE,
  KEY `ix_partner_images_partner_id` (`partner_id`) USING BTREE,
  CONSTRAINT `partner_images_ibfk_1` FOREIGN KEY (`partner_id`) REFERENCES `partners` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=81 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `partners` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `short_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `category` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `logo_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `icon_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `website_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `contact_email` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `contact_phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `sort_order` int DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_partners_id` (`id`) USING BTREE,
  KEY `ix_partners_branch_id` (`branch_id`) USING BTREE,
  CONSTRAINT `partners_ibfk_1` FOREIGN KEY (`branch_id`) REFERENCES `branch` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `permissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `permission_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `permission_name` (`permission_name`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=111 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `pickup` (
  `id` int NOT NULL AUTO_INCREMENT,
  `parentid` int DEFAULT NULL,
  `childid` int DEFAULT NULL,
  `branchid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pickMorning` time DEFAULT NULL,
  `pickAfternoon` time DEFAULT NULL,
  `date` date DEFAULT NULL,
  `academicid` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=141 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `pickup_branch_calling` (
  `academic_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `calling_enabled` tinyint(1) NOT NULL DEFAULT '0',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`academic_id`,`branch_id`) USING BTREE,
  KEY `idx_pbc_academic` (`academic_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `pickup_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `parent_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `pickup_branch_id` int DEFAULT NULL,
  `status` enum('pending','processing','completed','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `repeat_count` int NOT NULL,
  `current_repeat` int NOT NULL,
  `requested_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `processing_started_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `cooldown_until` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_pickup_requests_student_id` (`student_id`) USING BTREE,
  KEY `ix_pickup_requests_academic_id` (`academic_id`) USING BTREE,
  KEY `ix_pickup_requests_pickup_branch_id` (`pickup_branch_id`) USING BTREE,
  KEY `ix_pickup_requests_parent_id` (`parent_id`) USING BTREE,
  KEY `ix_pickup_requests_id` (`id`) USING BTREE,
  KEY `idx_pickup_academic_status_requested` (`academic_id`,`status`,`requested_at`,`id`) USING BTREE,
  KEY `idx_pickup_branch_queue` (`academic_id`,`pickup_branch_id`,`status`,`requested_at`,`id`) USING BTREE,
  KEY `idx_pickup_parent_student_latest` (`parent_id`,`student_id`,`id`) USING BTREE,
  KEY `idx_pickup_student_active` (`student_id`,`status`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=127 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `pickup_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academic_id` int NOT NULL,
  `repeat_count` int NOT NULL,
  `cooldown_seconds` int NOT NULL,
  `calling_enabled` tinyint(1) NOT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `ix_pickup_settings_academic_id` (`academic_id`) USING BTREE,
  KEY `ix_pickup_settings_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `position` (
  `id` int NOT NULL AUTO_INCREMENT,
  `position` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `translate` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `departmentId` int NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=42 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `price_list` (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `monthly` decimal(65,2) NOT NULL,
  `quarter` decimal(65,2) NOT NULL,
  `semester` decimal(65,2) NOT NULL,
  `oneyear` decimal(65,2) NOT NULL,
  `academicid` int NOT NULL,
  `branch_id` int NOT NULL,
  `note` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=188 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `price_visibility_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_id` int DEFAULT NULL COMMENT 'NULL = all branches',
  `program_id` int DEFAULT NULL COMMENT 'NULL = all programs',
  `show_monthly` tinyint(1) NOT NULL DEFAULT '1',
  `show_quarter` tinyint(1) NOT NULL DEFAULT '1',
  `show_semester` tinyint(1) NOT NULL DEFAULT '1',
  `show_oneyear` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `profile_frame_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `frame_id` int DEFAULT NULL,
  `generated_image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `user_id` (`user_id`) USING BTREE,
  KEY `frame_id` (`frame_id`) USING BTREE,
  KEY `ix_profile_frame_history_id` (`id`) USING BTREE,
  CONSTRAINT `profile_frame_history_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `profile_frame_history_ibfk_2` FOREIGN KEY (`frame_id`) REFERENCES `profile_frames` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=120 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `profile_frames` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `sort_order` int DEFAULT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `publish_at` datetime DEFAULT NULL,
  `expires_at` datetime DEFAULT NULL,
  `user_id` int DEFAULT NULL,
  `is_public` tinyint(1) NOT NULL DEFAULT '1',
  `is_featured` tinyint(1) NOT NULL DEFAULT '0',
  `slug` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `ix_profile_frames_slug` (`slug`) USING BTREE,
  KEY `user_id` (`user_id`) USING BTREE,
  KEY `ix_profile_frames_id` (`id`) USING BTREE,
  CONSTRAINT `profile_frames_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `program` (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `program_name_us` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `mark_type` varchar(25) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'kh',
  `short_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `academic_id` int NOT NULL,
  `report_status` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `head_user_id` int DEFAULT NULL,
  `time_report` time DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_by` int NOT NULL,
  `updated_by` int DEFAULT NULL,
  `noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `qrattendance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `attendance_date` date NOT NULL,
  `morning_in` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `morning_out` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `afternoon_in` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `afternoon_out` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `results_top_students` (
  `id` int NOT NULL AUTO_INCREMENT,
  `featured_batch_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `academic_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `shift_id` int NOT NULL,
  `grade_type_id` int DEFAULT NULL,
  `student_id` int NOT NULL,
  `rank` int NOT NULL,
  `average` decimal(10,2) DEFAULT NULL,
  `grade` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `marks_system_id` int DEFAULT NULL,
  `result_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `exam_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `exam_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `period` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` int NOT NULL,
  `featured_by` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_results_top_students_id` (`id`) USING BTREE,
  KEY `ix_results_top_students_marks_system_id` (`marks_system_id`) USING BTREE,
  KEY `ix_results_top_students_grade_type_id` (`grade_type_id`) USING BTREE,
  KEY `ix_results_top_students_shift_id` (`shift_id`) USING BTREE,
  KEY `ix_results_top_students_is_active` (`is_active`) USING BTREE,
  KEY `ix_results_top_students_program_id` (`program_id`) USING BTREE,
  KEY `ix_results_top_students_grade_id` (`grade_id`) USING BTREE,
  KEY `ix_results_top_students_student_id` (`student_id`) USING BTREE,
  KEY `ix_results_top_students_featured_batch_id` (`featured_batch_id`) USING BTREE,
  KEY `ix_results_top_students_academic_id` (`academic_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=367 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `results_top_students_display_settings` (
  `id` int NOT NULL,
  `avatar_chip_mode` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `hide_section` tinyint(1) NOT NULL DEFAULT '0',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `hide_medals_section` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `role_permissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `role_id` int NOT NULL,
  `permission_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_role_permission` (`role_id`,`permission_id`) USING BTREE,
  KEY `permission_id` (`permission_id`) USING BTREE,
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `role_permissions_ibfk_2` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=607 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `roles` (
  `id` int NOT NULL AUTO_INCREMENT,
  `role_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `salary_bonuses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int DEFAULT NULL,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `type` enum('FIXED_AMOUNT','HOURLY_RATE','PERCENTAGE') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` float NOT NULL,
  `is_enabled` tinyint(1) DEFAULT NULL,
  `effective_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_bonus_user` (`user_id`) USING BTREE,
  KEY `idx_bonus_type` (`type`) USING BTREE,
  KEY `idx_bonus_effective` (`effective_date`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `salary_deductions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int DEFAULT NULL,
  `attendance_setting_id` int DEFAULT NULL,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `type` enum('FIXED_AMOUNT','HOURLY_RATE','PERCENTAGE') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` float NOT NULL,
  `is_enabled` tinyint(1) DEFAULT NULL,
  `effective_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_deduction_user` (`user_id`) USING BTREE,
  KEY `idx_deduction_type` (`type`) USING BTREE,
  KEY `idx_deduction_effective` (`effective_date`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `salary_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `financial_id` int NOT NULL,
  `previous_amount` decimal(12,2) DEFAULT NULL,
  `new_amount` decimal(12,2) NOT NULL,
  `change_date` datetime DEFAULT CURRENT_TIMESTAMP,
  `reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `user_id` int NOT NULL,
  `base_salary` float NOT NULL,
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `effective_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_salary_history_financial` (`financial_id`) USING BTREE,
  KEY `idx_salary_history_change_date` (`change_date`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `scholarship` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `program_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=153 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `school_documents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `title_km` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `subtitle` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `subtitle_km` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `icon_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'description',
  `pdf_url` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_audience` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'all',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `sort_order` int NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_sd_active_order` (`is_active`,`sort_order`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `school_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `title_kh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_date` date NOT NULL,
  `event_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `round` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `participant_group` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `time_of_day` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `academic_year` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `color_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_school_events_academic_year` (`academic_year`) USING BTREE,
  KEY `ix_school_events_id` (`id`) USING BTREE,
  KEY `ix_school_events_event_date` (`event_date`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=42 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `school_overviews` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `icon_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `color_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sort_order` int DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  `title_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title_km` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `content_en` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `content_km` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_school_overviews_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `enterpriseName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `enterpriseType` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `eProvince` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `eDistrict` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `eCommune` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `eVillage` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `enterpriseAddress` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `ownerKname` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `ownerEname` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `ownerGender` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `ownerNationality` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `isForeigner` int NOT NULL,
  `prefixid` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `suffix` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `digit_number` int DEFAULT '6',
  `follow_type` enum('settings','branch') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'settings',
  `academicid` int NOT NULL,
  `startid` int DEFAULT NULL,
  `status_fixedexchange` varchar(3) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'no',
  `default_exchange` int NOT NULL DEFAULT '4100',
  `telegrambot` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `parent_bot_token` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `time_report` time DEFAULT NULL,
  `report_chat_id` varchar(25) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `report_status` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `skip_sat` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `skip_sun` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `time_allow_start` time NOT NULL,
  `time_allow_end` time NOT NULL,
  `marks_extraday` varchar(15) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT '5',
  `notify_parents` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'no',
  `system_logo` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `system_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `secret_pass` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `image_header` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `facebook_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `telegram_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `youtube_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `instagram_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `tiktok_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `active_storage_provider` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `cloudinary_cloud_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cloudinary_api_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cloudinary_api_secret` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `aws_access_key_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `aws_secret_access_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `aws_region_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `aws_bucket_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `firebase_storage_bucket` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `firebase_service_account_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `enable_schedule_reminders` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ota_updates_enabled` tinyint(1) NOT NULL,
  `phone_conflict_lock_enabled` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `shift` (
  `id` int NOT NULL AUTO_INCREMENT,
  `shift_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `shift_name_en` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `start_at` time DEFAULT NULL,
  `end_at` time DEFAULT NULL,
  `report_status` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `send_report_at` time DEFAULT NULL,
  `weeken_send` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'no',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `smart_download_links` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `android_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `ios_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `ix_smart_download_links_code` (`code`) USING BTREE,
  KEY `ix_smart_download_links_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `splash_ads` (
  `id` int NOT NULL AUTO_INCREMENT,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `duration_seconds` int NOT NULL,
  `target_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL,
  `start_date` datetime DEFAULT NULL,
  `end_date` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_splash_ads_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `status` (
  `id` int NOT NULL AUTO_INCREMENT,
  `status` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `student_activity_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `action_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `action_label` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `performed_by` int NOT NULL DEFAULT '0',
  `performed_by_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_form` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_student_id` (`student_id`) USING BTREE,
  KEY `idx_action_type` (`action_type`) USING BTREE,
  KEY `idx_created_at` (`created_at`) USING BTREE,
  KEY `idx_performed_by` (`performed_by`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=919 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `student_profile_edit_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `requested_by` int NOT NULL,
  `requested_by_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `kName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `eName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gender` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dob` date DEFAULT NULL,
  `is_foreigner` int DEFAULT NULL,
  `student_phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `province` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `district` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `commune` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `village` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `previousSchool` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `student_noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `branch` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `avatar` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `previous_values` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_student_profile_edit_requests_student_id` (`student_id`) USING BTREE,
  KEY `ix_student_profile_edit_requests_requested_by` (`requested_by`) USING BTREE,
  KEY `ix_student_profile_edit_requests_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=110 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `students` (
  `id` int NOT NULL AUTO_INCREMENT,
  `studentid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `optional_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `kName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `eName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `gender` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `dob` date NOT NULL,
  `image` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `student_phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_foreigner` int NOT NULL DEFAULT '1',
  `province` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `district` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `commune` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `village` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `previousSchool` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `leaveDate` datetime DEFAULT NULL,
  `myparents` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `child_order` int NOT NULL DEFAULT '1',
  `academic` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `branch` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` int NOT NULL,
  `student_noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `pickup_audio_url` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pickup_extra_branch_ids` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `submitted_by_parent` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_students_status` (`status`) USING BTREE,
  KEY `ix_students_branch` (`branch`) USING BTREE,
  KEY `ix_students_academic` (`academic`) USING BTREE,
  KEY `idx_students_branch_status` (`branch`,`status`) USING BTREE,
  KEY `idx_students_academic` (`academic`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1130 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `subject_attendance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `grade_type_id` int NOT NULL DEFAULT '0',
  `shift_id` int NOT NULL,
  `subject_id` int NOT NULL,
  `attendance_date` date NOT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `note` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `teacher_id` int NOT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_subject_attendance_context` (`student_id`,`academic_id`,`program_id`,`grade_id`,`grade_type_id`,`shift_id`,`subject_id`,`attendance_date`) USING BTREE,
  KEY `ix_subject_attendance_subject_date` (`academic_id`,`program_id`,`grade_id`,`grade_type_id`,`shift_id`,`subject_id`,`attendance_date`) USING BTREE,
  KEY `ix_subject_attendance_student` (`student_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=251 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `subject_grade_components` (
  `id` int NOT NULL AUTO_INCREMENT,
  `plan_id` int NOT NULL,
  `name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `weight_percent` decimal(7,2) NOT NULL,
  `source_type` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'manual',
  `sort_order` int NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_subject_grade_component_plan` (`plan_id`) USING BTREE,
  CONSTRAINT `fk_subject_grade_component_plan` FOREIGN KEY (`plan_id`) REFERENCES `subject_grade_plans` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `subject_grade_plans` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academic_id` int NOT NULL,
  `program_id` int NOT NULL,
  `grade_id` int NOT NULL,
  `grade_type_id` int NOT NULL DEFAULT '0',
  `shift_id` int NOT NULL,
  `subject_id` int NOT NULL,
  `marks_system_id` int NOT NULL,
  `attendance_end_date` date DEFAULT NULL,
  `attendance_start_date` date DEFAULT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_subject_grade_plan_context` (`academic_id`,`program_id`,`grade_id`,`grade_type_id`,`shift_id`,`subject_id`,`marks_system_id`) USING BTREE,
  KEY `ix_subject_grade_plan_subject` (`subject_id`) USING BTREE,
  KEY `ix_subject_grade_plan_exam` (`marks_system_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `subject_grade_scores` (
  `id` int NOT NULL AUTO_INCREMENT,
  `component_id` int NOT NULL,
  `student_id` int NOT NULL,
  `earned_points` decimal(7,2) NOT NULL,
  `updated_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_subject_grade_score_student` (`component_id`,`student_id`) USING BTREE,
  KEY `ix_subject_grade_score_student` (`student_id`) USING BTREE,
  CONSTRAINT `fk_subject_grade_score_component` FOREIGN KEY (`component_id`) REFERENCES `subject_grade_components` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `subjects` (
  `id` int NOT NULL AUTO_INCREMENT,
  `subject_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_name_us` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `program_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `updated_at` date NOT NULL,
  `created_at` date NOT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `short_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=53 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `subjects_group` (
  `id` int NOT NULL AUTO_INCREMENT,
  `grade_group_id` int NOT NULL,
  `program_id` int NOT NULL,
  `subject_id` int NOT NULL,
  `full_marks` decimal(10,2) NOT NULL,
  `calculate_marks` decimal(10,2) NOT NULL,
  `academic_id` int NOT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=215 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `teachers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `teacher_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `first_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `subject` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `department` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `hire_date` datetime DEFAULT CURRENT_TIMESTAMP,
  `salary` float DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `ix_teachers_teacher_id` (`teacher_id`) USING BTREE,
  UNIQUE KEY `ix_teachers_email` (`email`) USING BTREE,
  KEY `ix_teachers_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_attendance_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `bot_token` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `enabled` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `notify_leave_requests` tinyint(1) DEFAULT NULL,
  `notify_leave_decisions` tinyint(1) DEFAULT NULL,
  `leave_routing_mode` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `leave_chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `branch_routing_mode` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_telegram_attendance_settings_id` (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_bot_auth_codes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(6) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `expires_at` datetime NOT NULL,
  `used_at` datetime DEFAULT NULL,
  `used_for_chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `intended_role` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_tbac_code` (`code`) USING BTREE,
  KEY `idx_tbac_expires_at` (`expires_at`) USING BTREE,
  KEY `idx_tbac_used_at` (`used_at`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_branch_notification_routes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `settings_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `attendance_chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `leave_chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_telegram_branch_notification_route` (`settings_id`,`branch_id`) USING BTREE,
  KEY `ix_telegram_branch_notification_routes_id` (`id`) USING BTREE,
  KEY `ix_telegram_branch_notification_routes_settings_id` (`settings_id`) USING BTREE,
  KEY `ix_telegram_branch_notification_routes_branch_id` (`branch_id`) USING BTREE,
  CONSTRAINT `telegram_branch_notification_routes_ibfk_1` FOREIGN KEY (`settings_id`) REFERENCES `telegram_attendance_settings` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_chat_moderation_settings` (
  `chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `file_policy` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `blocked_extensions` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `allowed_extensions` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `link_policy` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `allowed_domains` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `exempt_admins` tinyint(1) NOT NULL DEFAULT '1',
  `send_warning` tinyint(1) NOT NULL DEFAULT '1',
  `updated_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`chat_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_group_members` (
  `id` int NOT NULL AUTO_INCREMENT,
  `telegram_user_id` bigint NOT NULL,
  `group_chat_id` bigint NOT NULL,
  `first_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `last_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `language_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_bot` tinyint(1) DEFAULT NULL,
  `phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `group_title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_verified` tinyint(1) DEFAULT NULL,
  `verified_at` datetime DEFAULT NULL,
  `joined_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_telegram_group_members_id` (`id`) USING BTREE,
  KEY `ix_telegram_group_members_group_chat_id` (`group_chat_id`) USING BTREE,
  KEY `ix_telegram_group_members_telegram_user_id` (`telegram_user_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1092 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_group_reply_settings` (
  `chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `features` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`chat_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_login_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `token` varchar(96) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `telegram_user_id` bigint DEFAULT NULL,
  `private_chat_id` bigint DEFAULT NULL,
  `phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `first_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `last_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `expires_at` datetime NOT NULL,
  `verified_at` datetime DEFAULT NULL,
  `consumed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `token` (`token`) USING BTREE,
  KEY `idx_tls_token` (`token`) USING BTREE,
  KEY `idx_tls_telegram_user_id` (`telegram_user_id`) USING BTREE,
  KEY `idx_tls_status_expires` (`status`,`expires_at`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_moderation_events` (
  `event_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `message_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `telegram_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `content_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `domain` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`event_id`) USING BTREE,
  KEY `idx_tme_chat_id` (`chat_id`) USING BTREE,
  KEY `idx_tme_created_at` (`created_at`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_moderation_quarantine_items` (
  `chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `message_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `media_group_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `message_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `violation_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_key`,`message_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_otp_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `phone_code_hash` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_string` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `expires_at` datetime NOT NULL,
  `used_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `registration_token_hash` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `registration_expires_at` datetime DEFAULT NULL,
  `registration_used_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_telegram_otp_sessions_phone` (`phone`) USING BTREE,
  KEY `idx_tos_phone` (`phone`) USING BTREE,
  KEY `idx_tos_expires` (`expires_at`) USING BTREE,
  KEY `idx_tos_registration_token` (`registration_token_hash`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1335 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_tracked_chats` (
  `id` int NOT NULL AUTO_INCREMENT,
  `chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Telegram chat ID',
  `chat_title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Group/channel name',
  `chat_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'private, group, supergroup, channel',
  `is_active` tinyint(1) DEFAULT '1' COMMENT 'Bot still in chat',
  `added_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'When bot was added',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `bot_role` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'pending' COMMENT 'pending, notification_only, general',
  `bot_token` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Telegram bot token that owns this chat',
  `member_verification_enabled` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Require new members to verify before chatting',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `chat_id` (`chat_id`) USING BTREE,
  KEY `idx_chat_id` (`chat_id`) USING BTREE,
  KEY `idx_active` (`is_active`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=152 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `telegram_webhook_events` (
  `event_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `update_id` bigint DEFAULT NULL,
  `chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `telegram_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `claim_token` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `processed_at` datetime(6) NOT NULL,
  PRIMARY KEY (`event_key`) USING BTREE,
  KEY `idx_twe_processed_at` (`processed_at`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `units` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(25) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=34 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `user_financials` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `bank_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bank_account_number` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bank_account_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `nssf_number` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `nssf_employee_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `spouse_status` tinyint(1) DEFAULT NULL,
  `dependent_count` int DEFAULT NULL,
  `is_resident` tinyint(1) DEFAULT NULL,
  `base_salary` decimal(12,2) DEFAULT NULL,
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_user_financials` (`user_id`) USING BTREE,
  KEY `idx_financials_user` (`user_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `user_home_app_permissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `feature_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_allowed` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_user_home_feature` (`user_id`,`feature_id`) USING BTREE,
  KEY `ix_user_home_app_permissions_user_id` (`user_id`) USING BTREE,
  KEY `ix_user_home_app_permissions_feature_id` (`feature_id`) USING BTREE,
  KEY `ix_user_home_app_permissions_id` (`id`) USING BTREE,
  CONSTRAINT `user_home_app_permissions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=80 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `user_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `telegram_id` bigint NOT NULL,
  `user_id` int DEFAULT NULL,
  `username` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `session_data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `login_time` datetime DEFAULT NULL,
  `is_logged_in` tinyint(1) DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `last_activity` datetime DEFAULT CURRENT_TIMESTAMP,
  `ban_until` datetime DEFAULT NULL,
  `login_tier` int DEFAULT '0',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `telegram_id` (`telegram_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1166 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `uniqueId` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `image` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `kName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `eName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `height` decimal(10,2) NOT NULL,
  `gender` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `dob` date NOT NULL,
  `signature` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `nationality` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `religion` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `province` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `district` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `commune` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `village` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `phone` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `telegramId` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pProvince` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pDistrict` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pCommune` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pVillage` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `identityNumber` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `identityRegDate` date DEFAULT NULL,
  `identityEndDate` date DEFAULT NULL,
  `identityRegPlace` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fatherName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `motherName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `departmentId` int DEFAULT NULL,
  `positionId` int DEFAULT NULL,
  `startWork` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `endWork` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `education` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `workplace` int NOT NULL,
  `status` int NOT NULL,
  `role` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `isForeigner` int NOT NULL,
  `bankAccountNumber` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bankAccountName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bankName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `baseSalary` decimal(10,2) DEFAULT NULL,
  `nssfNumber` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `isNssf` int DEFAULT '0',
  `isResident` int DEFAULT '1',
  `hasSpouse` int DEFAULT '0',
  `numberOfDependents` int DEFAULT '0',
  `token_version` int DEFAULT NULL,
  `signatureImagePath` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_users_workplace_role_status` (`workplace`,`role`,`status`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=169 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `users_resource` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `user_type` enum('teacher','student','parent','employee') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `avatar` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cover_image` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bio` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `status_message` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `website` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `cover_focus_y` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_user_resource_owner` (`user_id`,`user_type`) USING BTREE,
  KEY `ix_users_resource_user_id` (`user_id`) USING BTREE,
  KEY `ix_users_resource_id` (`id`) USING BTREE,
  KEY `ix_users_resource_user_type` (`user_type`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=26177 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `users_social_links` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_resource_id` int NOT NULL,
  `platform_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `link` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `user_resource_id` (`user_resource_id`) USING BTREE,
  KEY `ix_users_social_links_id` (`id`) USING BTREE,
  CONSTRAINT `users_social_links_ibfk_1` FOREIGN KEY (`user_resource_id`) REFERENCES `users_resource` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `work_locations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `latitude` float(10,8) NOT NULL,
  `longitude` float(11,8) NOT NULL,
  `radius_meters` int NOT NULL DEFAULT '100',
  `branch_id` int DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` int DEFAULT NULL,
  `updated_by` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_location_branch` (`branch_id`) USING BTREE,
  KEY `idx_location_active` (`is_active`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ws_broadcast_queue` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `channel` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` json NOT NULL,
  `created_at` timestamp(3) NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_ws_channel_created` (`channel`,`created_at`) USING BTREE,
  KEY `idx_ws_created` (`created_at`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=83305 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `zing_book_branch_limits` (
  `id` int NOT NULL AUTO_INCREMENT,
  `book_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `max_count` int NOT NULL DEFAULT '0',
  `current_count` int NOT NULL DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_book_branch` (`book_id`,`branch_id`) USING BTREE,
  CONSTRAINT `zing_book_branch_limits_ibfk_1` FOREIGN KEY (`book_id`) REFERENCES `zing_books` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=1288 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `zing_book_support` (
  `id` int NOT NULL AUTO_INCREMENT,
  `book_id` int DEFAULT NULL,
  `parent_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `academic_id` int DEFAULT NULL,
  `amount` decimal(10,2) NOT NULL,
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'USD',
  `supporter_type` enum('parent','teacher','normal_user') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'parent',
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `status` enum('pending','confirmed','completed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `payment_method_id` int DEFAULT NULL,
  `payment_receipt` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `quantity` int DEFAULT '1',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `book_id` (`book_id`) USING BTREE,
  KEY `payment_method_id` (`payment_method_id`) USING BTREE,
  CONSTRAINT `zing_book_support_ibfk_1` FOREIGN KEY (`book_id`) REFERENCES `zing_books` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `zing_book_support_ibfk_2` FOREIGN KEY (`payment_method_id`) REFERENCES `zing_payment_methods` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=60 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `zing_book_support_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `support_id` int NOT NULL,
  `action` enum('create','update_status','update','delete') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `previous_status` enum('pending','confirmed','completed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `new_status` enum('pending','confirmed','completed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `previous_amount` decimal(10,2) DEFAULT NULL,
  `new_amount` decimal(10,2) DEFAULT NULL,
  `changed_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `support_id` (`support_id`) USING BTREE,
  CONSTRAINT `zing_book_support_history_ibfk_1` FOREIGN KEY (`support_id`) REFERENCES `zing_book_support` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=60 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `zing_books` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `title_kh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `author` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `isbn` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `level` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `category` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `size_label` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `color` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `pages` int DEFAULT NULL,
  `price` decimal(10,2) NOT NULL,
  `price_khr` decimal(12,2) DEFAULT NULL,
  `quantity` int NOT NULL DEFAULT '0',
  `total_price` decimal(12,2) NOT NULL DEFAULT '0.00',
  `supported_quantity` int NOT NULL DEFAULT '0',
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'USD',
  `cover_image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `display_max_price` tinyint(1) DEFAULT '1',
  `is_active` tinyint(1) DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=796 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `zing_payment_methods` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `display_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `payment_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT '1',
  `display_order` int DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `zing_survey_questions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `survey_id` int NOT NULL,
  `question_text_en` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_text_kh` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_type` enum('text','textarea','radio','checkbox','select','number','date') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `options` json DEFAULT NULL,
  `is_required` tinyint(1) DEFAULT '1',
  `order_index` int DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `survey_id` (`survey_id`) USING BTREE,
  CONSTRAINT `zing_survey_questions_ibfk_1` FOREIGN KEY (`survey_id`) REFERENCES `zing_surveys` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `zing_survey_responses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `survey_id` int NOT NULL,
  `parent_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `branch_id` int DEFAULT NULL,
  `program_id` int DEFAULT NULL,
  `number_of_children` int DEFAULT NULL,
  `children_names` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `response_data` json NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_read` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `survey_id` (`survey_id`) USING BTREE,
  CONSTRAINT `zing_survey_responses_ibfk_1` FOREIGN KEY (`survey_id`) REFERENCES `zing_surveys` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `zing_surveys` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `title_kh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description_en` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `description_kh` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `allow_public` tinyint(1) DEFAULT '1',
  `allow_private` tinyint(1) DEFAULT '1',
  `is_active` tinyint(1) DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==========================================
-- 2. SEED DEFAULT REFERENCE DATA
-- ==========================================

-- Default seed data for `roles` (13 rows)
INSERT INTO `roles` (`id`, `role_name`, `created_at`, `updated_at`) VALUES
  (1, 'Super Admin', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (2, 'Teacher', '2025-07-21 19:27:26', '2025-08-04 10:57:01'),
  (3, 'Admin', '2025-07-21 19:27:26', '2025-08-04 10:56:52'),
  (4, 'Accountant', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (5, 'Reception', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (6, 'Viewer', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (7, 'Principal', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (8, 'Counselor', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (9, 'Librarian', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (10, 'Registrar', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (11, 'ITSupport', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (12, 'Parent', '2025-07-21 19:27:26', '2025-07-21 19:27:26'),
  (13, 'Student', '2025-07-21 19:27:26', '2025-07-21 19:27:26')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `permissions` (109 rows)
INSERT INTO `permissions` (`id`, `permission_name`, `description`, `created_at`, `updated_at`) VALUES
  (1, 'ViewStudent', 'View student information', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (2, 'AddStudent', 'Add new students', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (3, 'UpdateStudent', 'Edit student details', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (4, 'DeleteStudent', 'Delete student records', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (5, 'ViewTeacher', 'View teacher information', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (6, 'AddTeacher', 'Add new teachers', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (7, 'UpdateTeacher', 'Edit teacher details', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (8, 'DeleteTeacher', 'Remove teacher records', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (9, 'ViewClass', 'View classes or courses', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (10, 'AddClass', 'Add new classes or courses', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (11, 'UpdateClass', 'Edit class/course details', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (12, 'DeleteClass', 'Delete classes', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (13, 'ViewAttendance', 'View attendance records', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (14, 'AddAttendance', 'Add attendance records', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (15, 'UpdateAttendance', 'Edit attendance', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (16, 'DeleteAttendance', 'Delete attendance records', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (17, 'ViewGrades', 'View student grades', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (18, 'AddGrades', 'Enter grades', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (19, 'UpdateGrades', 'Edit grades', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (20, 'DeleteGrades', 'Remove grades', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (21, 'ViewReports', 'View various reports', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (22, 'GenerateReports', 'Generate or export reports', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (23, 'ManageUsers', 'Manage user accounts and roles', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (24, 'ManageRoles', 'Create/edit/delete roles and permissions', '2025-07-21 19:18:39', '2025-07-21 19:18:39'),
  (25, 'ViewAllBranches', 'View all Branch', '2025-07-21 20:37:25', '2025-07-21 20:37:25'),
  (26, 'ViewAdminDashboard', NULL, '2025-07-21 21:05:16', '2025-07-21 21:05:16'),
  (27, 'ViewTeacherDashboard', '', '2025-07-21 21:05:16', '2025-07-21 21:05:16'),
  (28, 'DeleteReceipt', 'Delete invoice', '2025-07-29 07:40:49', '2025-07-29 07:41:42'),
  (29, 'ViewAccounts', NULL, '2025-08-04 16:22:58', '2025-08-04 16:22:58'),
  (30, 'ViewReceipt', NULL, '2025-08-04 16:25:51', '2025-08-04 16:25:51'),
  (31, 'ChangeRole', NULL, '2025-08-04 17:13:43', '2025-08-04 17:13:43'),
  (32, 'UserPassword', NULL, '2025-08-04 17:29:11', '2025-08-04 17:29:11'),
  (34, 'ClearAccounts', NULL, '2025-08-04 17:44:14', '2025-08-04 17:44:14'),
  (35, 'UpdateSettings', NULL, '2025-08-04 17:48:54', '2025-08-04 17:48:54'),
  (36, 'DashboardBasic', NULL, '2025-08-10 20:55:34', '2025-08-10 20:55:34'),
  (37, 'DashboardAccounting', NULL, '2025-08-10 20:55:55', '2025-08-10 20:55:55'),
  (38, 'GeneralDelete', NULL, '2025-08-19 09:11:20', '2025-08-19 09:11:20'),
  (39, 'GeneralUpdate', NULL, '2025-08-19 09:11:39', '2025-08-19 09:11:39'),
  (40, 'GeneralAdd', NULL, '2025-08-19 09:11:59', '2025-08-19 09:11:59'),
  (41, 'AdminViewApp', 'View App settings', '2026-01-13 02:30:00', '2026-01-13 02:30:00'),
  (42, 'AdminUpdateApp', 'Update App settings', '2026-01-13 02:30:01', '2026-01-13 02:30:01'),
  (43, 'AdminDeleteApp', 'Delete App settings', '2026-01-13 02:30:01', '2026-01-13 02:30:01'),
  (44, 'ViewInvoices', NULL, '2026-06-15 02:47:21', '2026-06-15 02:47:21'),
  (45, 'ViewUpcomingInvoices', NULL, '2026-06-15 02:47:22', '2026-06-15 02:47:22'),
  (46, 'ViewInventories', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (47, 'ViewPricing', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (48, 'ViewFeeServices', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (49, 'AddAccount', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (50, 'EditAccount', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (51, 'EditInvoice', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (52, 'AddInventory', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (53, 'EditInventory', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (54, 'DeleteInventory', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (55, 'AddPricing', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (56, 'EditPricing', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (57, 'DeletePricing', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (58, 'AddFeeService', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (59, 'EditFeeService', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (60, 'DeleteFeeService', NULL, '2026-06-15 02:47:23', '2026-06-15 02:47:23'),
  (61, 'AddDiscount', NULL, '2026-06-15 02:47:24', '2026-06-15 02:47:24'),
  (62, 'EditDiscount', NULL, '2026-06-15 02:47:24', '2026-06-15 02:47:24'),
  (63, 'DeleteDiscount', NULL, '2026-06-15 02:47:24', '2026-06-15 02:47:24'),
  (64, 'ViewDashboard', NULL, '2026-06-15 02:47:24', '2026-06-15 02:47:24'),
  (65, 'ViewStudents', NULL, '2026-06-15 02:47:24', '2026-06-15 02:47:24'),
  (66, 'ViewStudentsByClass', NULL, '2026-06-15 02:47:24', '2026-06-15 02:47:24'),
  (67, 'ViewStudentTeachers', NULL, '2026-06-15 02:47:24', '2026-06-15 02:47:24'),
  (68, 'ViewStudentPrograms', NULL, '2026-06-15 02:47:26', '2026-06-15 02:47:26'),
  (69, 'ViewScholarship', NULL, '2026-06-15 02:47:26', '2026-06-15 02:47:26'),
  (70, 'ViewCertificate', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (71, 'ViewMedals', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (72, 'ViewAchievement', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (73, 'ViewStoppedStudents', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (74, 'ViewParents', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (75, 'ViewParentPayments', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (76, 'ViewParentPickupReport', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (77, 'ViewEmployees', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (78, 'ViewPendingEmployees', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (79, 'ViewStoppedEmployees', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (80, 'ViewDepartments', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (81, 'ViewClassTeacherAssignment', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (82, 'ViewCalendar', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (83, 'ViewAcademic', NULL, '2026-06-15 02:47:27', '2026-06-15 02:47:27'),
  (84, 'ViewBranch', NULL, '2026-06-15 02:47:28', '2026-06-15 02:47:28'),
  (85, 'ViewGradeTypes', NULL, '2026-06-15 02:47:28', '2026-06-15 02:47:28'),
  (86, 'ViewGradeGroups', NULL, '2026-06-15 02:47:28', '2026-06-15 02:47:28'),
  (87, 'ViewPrograms', NULL, '2026-06-15 02:47:28', '2026-06-15 02:47:28'),
  (88, 'ViewShifts', NULL, '2026-06-15 02:47:29', '2026-06-15 02:47:29'),
  (89, 'ViewExamSystem', NULL, '2026-06-15 02:47:29', '2026-06-15 02:47:29'),
  (90, 'ViewMarksSystem', NULL, '2026-06-15 02:47:29', '2026-06-15 02:47:29'),
  (91, 'ViewMarkSubjects', NULL, '2026-06-15 02:47:30', '2026-06-15 02:47:30'),
  (92, 'ViewSubjects', NULL, '2026-06-15 02:47:30', '2026-06-15 02:47:30'),
  (93, 'ViewSubjectGroups', NULL, '2026-06-15 02:47:30', '2026-06-15 02:47:30'),
  (94, 'ViewNites', NULL, '2026-06-15 02:47:30', '2026-06-15 02:47:30'),
  (95, 'ViewExpense', NULL, '2026-06-15 02:47:30', '2026-06-15 02:47:30'),
  (96, 'ViewExpenseCategories', NULL, '2026-06-15 02:47:30', '2026-06-15 02:47:30'),
  (97, 'AddExpense', NULL, '2026-06-15 02:47:30', '2026-06-15 02:47:30'),
  (98, 'EditExpense', NULL, '2026-06-15 02:47:30', '2026-06-15 02:47:30'),
  (99, 'DeleteExpense', NULL, '2026-06-15 02:47:30', '2026-06-15 02:47:30'),
  (100, 'AddExpenseCategory', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (101, 'EditExpenseCategory', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (102, 'DeleteExpenseCategory', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (103, 'ViewBuses', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (104, 'ViewBusAttendance', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (105, 'ViewBusStops', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (106, 'ViewBusStopPrices', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (107, 'ViewBusDriverAssignment', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (108, 'ViewBusStudentEnrollment', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (109, 'ViewActivityLogs', NULL, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (110, 'ReviewStudentProfileEdits', NULL, '2026-08-24 02:44:41', '2026-08-24 02:44:41')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `role_permissions` (213 rows)
INSERT INTO `role_permissions` (`id`, `role_id`, `permission_id`, `created_at`, `updated_at`) VALUES
  (32, 2, 1, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (33, 2, 25, '2025-07-21 20:11:07', '2025-07-21 21:12:51'),
  (34, 2, 3, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (35, 2, 4, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (36, 2, 5, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (37, 2, 6, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (38, 2, 7, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (39, 2, 8, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (40, 2, 9, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (41, 2, 10, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (42, 2, 11, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (120, 12, 13, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (121, 13, 14, '2025-07-21 20:11:07', '2025-07-21 20:11:07'),
  (126, 2, 26, '2025-07-21 21:08:38', '2025-07-21 21:08:38'),
  (248, 5, 2, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (249, 5, 22, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (250, 5, 3, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (251, 5, 26, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (252, 5, 9, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (253, 5, 17, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (254, 5, 30, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (255, 5, 21, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (256, 5, 1, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (257, 5, 5, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (258, 5, 36, '2025-08-10 14:01:17', '2025-08-10 14:01:17'),
  (259, 6, 10, '2025-08-10 14:01:21', '2025-08-10 14:01:21'),
  (260, 6, 6, '2025-08-10 14:01:21', '2025-08-10 14:01:21'),
  (261, 6, 4, '2025-08-10 14:01:21', '2025-08-10 14:01:21'),
  (262, 6, 11, '2025-08-10 14:01:21', '2025-08-10 14:01:21'),
  (263, 6, 7, '2025-08-10 14:01:21', '2025-08-10 14:01:21'),
  (264, 6, 5, '2025-08-10 14:01:21', '2025-08-10 14:01:21'),
  (265, 6, 36, '2025-08-10 14:01:21', '2025-08-10 14:01:21'),
  (291, 9, 11, '2025-08-10 14:01:45', '2025-08-10 14:01:45'),
  (292, 9, 9, '2025-08-10 14:01:45', '2025-08-10 14:01:45'),
  (293, 9, 36, '2025-08-10 14:01:45', '2025-08-10 14:01:45'),
  (294, 8, 8, '2025-08-10 14:01:50', '2025-08-10 14:01:50'),
  (295, 8, 11, '2025-08-10 14:01:50', '2025-08-10 14:01:50'),
  (296, 8, 36, '2025-08-10 14:01:50', '2025-08-10 14:01:50'),
  (297, 7, 10, '2025-08-10 14:01:57', '2025-08-10 14:01:57'),
  (298, 7, 6, '2025-08-10 14:01:57', '2025-08-10 14:01:57'),
  (299, 7, 7, '2025-08-10 14:01:57', '2025-08-10 14:01:57'),
  (300, 7, 5, '2025-08-10 14:01:57', '2025-08-10 14:01:57'),
  (301, 7, 37, '2025-08-10 14:01:57', '2025-08-10 14:01:57'),
  (302, 7, 36, '2025-08-10 14:01:57', '2025-08-10 14:01:57'),
  (303, 4, 2, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (304, 4, 6, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (305, 4, 22, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (306, 4, 11, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (307, 4, 3, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (308, 4, 29, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (309, 4, 26, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (310, 4, 25, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (311, 4, 9, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (312, 4, 30, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (313, 4, 21, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (314, 4, 1, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (315, 4, 5, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (316, 4, 36, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (317, 4, 37, '2025-08-10 14:02:08', '2025-08-10 14:02:08'),
  (368, 3, 10, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (369, 3, 2, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (370, 3, 6, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (371, 3, 37, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (372, 3, 36, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (373, 3, 4, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (374, 3, 8, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (375, 3, 11, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (376, 3, 3, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (377, 3, 7, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (378, 3, 9, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (379, 3, 5, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (380, 3, 40, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (381, 3, 38, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (382, 3, 39, '2025-08-19 02:14:43', '2025-08-19 02:14:43'),
  (468, 3, 41, '2026-01-13 02:30:01', '2026-01-13 02:30:01'),
  (469, 3, 42, '2026-01-13 02:30:01', '2026-01-13 02:30:01'),
  (470, 3, 43, '2026-01-13 02:30:01', '2026-01-13 02:30:01'),
  (471, 1, 14, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (472, 1, 10, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (473, 1, 18, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (474, 1, 2, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (475, 1, 6, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (476, 1, 31, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (477, 1, 34, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (478, 1, 37, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (479, 1, 36, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (480, 1, 16, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (481, 1, 12, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (482, 1, 20, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (483, 1, 28, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (484, 1, 4, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (485, 1, 8, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (486, 1, 40, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (487, 1, 38, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (488, 1, 39, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (489, 1, 22, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (490, 1, 24, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (491, 1, 23, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (492, 1, 15, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (493, 1, 11, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (494, 1, 19, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (495, 1, 35, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (496, 1, 3, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (497, 1, 7, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (498, 1, 32, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (499, 1, 29, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (500, 1, 26, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (501, 1, 25, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (502, 1, 13, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (503, 1, 9, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (504, 1, 17, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (505, 1, 30, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (506, 1, 21, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (507, 1, 1, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (508, 1, 5, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (509, 1, 43, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (510, 1, 42, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (511, 1, 41, '2026-02-10 01:41:40', '2026-02-10 01:41:40'),
  (512, 1, 44, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (513, 1, 45, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (514, 1, 46, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (515, 1, 47, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (516, 1, 48, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (517, 1, 49, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (518, 1, 50, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (519, 1, 51, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (520, 1, 52, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (521, 1, 53, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (522, 1, 54, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (523, 1, 55, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (524, 1, 56, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (525, 1, 57, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (526, 1, 58, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (527, 1, 59, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (528, 1, 60, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (529, 1, 61, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (530, 1, 62, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (531, 1, 63, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (532, 1, 64, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (533, 1, 65, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (534, 1, 66, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (535, 1, 67, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (536, 1, 68, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (537, 1, 69, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (538, 1, 70, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (539, 1, 71, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (540, 1, 72, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (541, 1, 73, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (542, 1, 74, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (543, 1, 75, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (544, 1, 76, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (545, 1, 77, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (546, 1, 78, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (547, 1, 79, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (548, 1, 80, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (549, 1, 81, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (550, 1, 82, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (551, 1, 83, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (552, 1, 84, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (553, 1, 85, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (554, 1, 86, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (555, 1, 87, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (556, 1, 88, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (557, 1, 89, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (558, 1, 90, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (559, 1, 91, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (560, 1, 92, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (561, 1, 93, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (562, 1, 94, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (563, 1, 95, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (564, 1, 96, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (565, 1, 97, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (566, 1, 98, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (567, 1, 99, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (568, 1, 100, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (569, 1, 101, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (570, 1, 102, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (571, 1, 103, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (572, 1, 104, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (573, 1, 105, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (574, 1, 106, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (575, 1, 107, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (576, 1, 108, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (577, 1, 109, '2026-06-15 02:47:31', '2026-06-15 02:47:31'),
  (578, 1, 27, '2026-06-19 01:18:33', '2026-06-19 01:18:33'),
  (579, 2, 64, '2026-08-18 10:18:36', '2026-08-18 10:18:36'),
  (580, 3, 64, '2026-08-18 10:18:37', '2026-08-18 10:18:37'),
  (581, 4, 64, '2026-08-18 10:18:37', '2026-08-18 10:18:37'),
  (582, 5, 64, '2026-08-18 10:18:38', '2026-08-18 10:18:38'),
  (583, 6, 64, '2026-08-18 10:18:38', '2026-08-18 10:18:38'),
  (584, 7, 64, '2026-08-18 10:18:38', '2026-08-18 10:18:38'),
  (585, 8, 64, '2026-08-18 10:18:39', '2026-08-18 10:18:39'),
  (586, 9, 64, '2026-08-18 10:18:39', '2026-08-18 10:18:39'),
  (587, 10, 64, '2026-08-18 10:18:39', '2026-08-18 10:18:39'),
  (588, 10, 36, '2026-08-18 10:18:39', '2026-08-18 10:18:39'),
  (589, 10, 65, '2026-08-18 10:18:39', '2026-08-18 10:18:39'),
  (590, 10, 66, '2026-08-18 10:18:39', '2026-08-18 10:18:39'),
  (591, 10, 68, '2026-08-18 10:18:39', '2026-08-18 10:18:39'),
  (592, 10, 2, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (593, 10, 74, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (594, 10, 75, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (595, 10, 76, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (596, 10, 82, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (597, 10, 44, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (598, 10, 45, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (599, 10, 47, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (600, 10, 48, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (601, 11, 64, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (602, 11, 36, '2026-08-18 10:18:40', '2026-08-18 10:18:40'),
  (603, 12, 64, '2026-08-18 10:18:41', '2026-08-18 10:18:41'),
  (604, 13, 64, '2026-08-18 10:18:41', '2026-08-18 10:18:41'),
  (605, 1, 110, '2026-08-24 02:44:48', '2026-08-24 02:44:48'),
  (606, 3, 110, '2026-08-24 08:17:36', '2026-08-24 08:17:36')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `status` (5 rows)
INSERT INTO `status` (`id`, `status`, `updated_at`, `created_at`) VALUES
  (1, 'Active', '2025-03-31 09:45:02', '2026-01-06 07:11:39'),
  (2, 'Inactive', '2025-03-31 09:45:02', '2026-01-06 07:11:39'),
  (3, 'Suspended', '2025-03-31 09:45:02', '2026-01-06 07:11:39'),
  (4, 'Finished', '2025-03-31 09:45:02', '2026-01-06 07:11:39'),
  (5, 'Banned', '2025-03-31 09:45:02', '2026-01-06 07:11:39')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `position` (40 rows)
INSERT INTO `position` (`id`, `position`, `translate`, `departmentId`, `updated_at`, `created_at`) VALUES
  (1, 'Chairman of Board of Directors', 'ប្រធានក្រុមប្រឹក្សាភិបាល', 1, '2025-07-05 15:14:31', '2025-06-10 13:13:25'),
  (2, 'Member of Board of Director', 'សមាជិកក្រុមប្រឹក្សាភិបាល', 1, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (3, 'Director', 'នាយក', 2, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (4, 'Vice Director', 'នាយករង', 2, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (5, 'Senior Advisor of Academy', 'ទីប្រឹក្សាជាន់ខ្ពស់ផ្នែកសិក្សាធិការ', 2, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (6, 'Senior Advisor of Curriculum Development', 'ទីប្រឹក្សាជាន់ខ្ពស់ផ្នែកអភិវឌ្ឍកម្មវិធីសិក្សា', 2, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (7, 'Head of HR', 'ប្រធានផ្នែកធនធានមនុស្ស', 3, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (8, 'Training Coordinator', 'ប្រធានផ្នែកបណ្តុះបណ្តាល', 3, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (9, 'Assistant to HR', 'ជំនួយការធនធានមនុស្ស', 3, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (10, 'Head of Admin', 'ប្រធានផ្នែករដ្ឋបាល', 4, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (11, 'Admin Assistant', 'ជំនួយការរដ្ឋបាល', 4, '2025-04-22 11:10:51', '2025-06-10 13:13:25'),
  (13, 'Cleaner and Gardener', 'អ្នកសម្អាត និងថែទាំសួន', 4, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (14, 'Security Guard-Gardener-Cleaner', 'សន្តិសុខ ថែសួន និងសម្អាត', 4, '2025-06-03 08:09:26', '2025-06-10 13:13:25'),
  (15, 'Driver-Security Guards', 'អ្នកបើកបរ និងសន្តិសុខ', 4, '2025-06-03 09:15:05', '2025-06-10 13:13:25'),
  (16, 'Driver-Security Guards-Cleaner', 'អ្នកបើកបរ សន្តិសុខ និងសម្អាត', 4, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (17, 'Security Guards-Cleaner', 'សន្តិសុខអនាម័យ', 4, '2025-06-03 08:08:14', '2025-06-10 13:13:25'),
  (18, 'Gardener', 'មន្ត្រីផ្នែកកសិកម្ម', 4, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (19, 'Head of Finance', 'ប្រធានផ្នែកហិរញ្ញវត្តុ', 5, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (20, 'Cashier', 'បេឡាធិការ/បេឡាធិការិនី', 5, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (21, 'Accountant', 'គណនេយ្យករ', 5, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (22, 'Financial assistant', 'ជំនួយការហិរញ្ញវត្ថុ', 5, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (23, 'Accounting Assistant', 'ជំនួយការគណនេយ្យ', 5, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (24, 'Head of IT', 'ប្រធានព័ត៌មានវិទ្យា', 6, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (25, 'Digital Marketer', 'មន្ត្រីម៉ាឃីតធីងឌីជីថល', 6, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (26, 'IT Supporter', 'ជំនួយការព័ត៌មានវិទ្យា', 6, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (27, 'Camera Woman', 'មន្ត្រីផ្នែកថតរូប​ (ស្រី)', 6, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (28, 'Camera Man', 'មន្ត្រីផ្នែកថតរូប (ប្រុស)', 6, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (29, 'Admin & Program Supporter', 'ជំនួយការរដ្ឋបាល និងដំណើរការកម្មវិធី', 7, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (30, 'Head of Academy', 'ប្រធានសិក្សាធិការ', 8, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (31, 'Head of Teacher', 'ប្រធានគ្រូ', 8, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (32, 'Academic Assistant', 'ជំនួយការសិក្សាធិការ', 8, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (33, 'Head Teacher Assistant', 'ជំំនួយការប្រធានគ្រូ', 8, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (34, 'Teacher', 'គ្រូបង្រៀន', 8, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (35, 'Chinese Teacher', 'គ្រូបង្រៀនភាសាចិន', 8, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (36, 'English Teacher', 'គ្រូបង្រៀនភាសាអង់គ្លេស', 8, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (37, 'Teacher Assistant', 'ជំនួយការគ្រូ', 8, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (38, 'Internship Teacher', 'គ្រូបង្រៀនហាត់ការ', 8, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (39, 'Head of Part Time Teacher', 'ប្រធានគ្រូបង្រៀនក្រៅម៉ោង', 9, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (40, 'Assistant to Head of Part time Teacher', 'ជំនួយការប្រធានគ្រូបង្រៀនក្រៅម៉ោង', 9, '2025-03-31 14:22:28', '2025-06-10 13:13:25'),
  (41, 'Part time Teacher', 'គ្រូបង្រៀនក្រៅម៉ោង', 9, '2025-03-31 14:22:28', '2025-06-10 13:13:25')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `department` (9 rows)
INSERT INTO `department` (`id`, `department`, `translate`, `code`, `updated_at`, `created_at`) VALUES
  (1, 'Board of Directors', 'ក្រុមប្រឹក្សាភិបាល', 'BDD', '2025-03-31 14:22:09', '2025-06-10 13:10:54'),
  (2, 'Management Team', 'គណៈគ្រប់គ្រង', 'MTD', '2025-03-31 14:22:09', '2025-06-10 13:10:54'),
  (3, 'Human Resource​ ', 'ផ្នែកធនធានមនុស្ស', 'HRD', '2025-03-31 14:22:09', '2025-06-10 13:10:54'),
  (4, 'Administrative', 'ផ្នែករដ្ឋបាល', 'AD', '2025-03-31 14:22:09', '2025-06-10 13:10:54'),
  (5, 'Financial', 'ផ្នែកហិរញ្ញវត្ថុ', 'FD', '2025-03-31 14:22:09', '2025-06-10 13:10:54'),
  (6, 'Information Technology', 'ផ្នែកព័ត៌មានវិទ្យា', 'ITD', '2025-03-31 14:22:09', '2025-06-10 13:10:54'),
  (7, 'Marketing', 'ផ្នែកទីផ្សារ', 'MD', '2025-03-31 14:22:09', '2025-06-10 13:10:54'),
  (8, 'Full Time Academic', 'ផ្នែកសិក្សាធិការ (ពេញម៉ោង)', 'FTD', '2025-03-31 14:22:09', '2025-06-10 13:10:54'),
  (9, 'Part Time Academic', 'ផ្នែកសិក្សាធិការ (ក្រៅម៉ោង)', 'PTD', '2025-03-31 14:22:09', '2025-06-10 13:10:54')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `shift` (2 rows)
INSERT INTO `shift` (`id`, `shift_name`, `shift_name_en`, `start_at`, `end_at`, `report_status`, `send_report_at`, `weeken_send`, `created_at`, `updated_at`) VALUES
  (1, 'វេនព្រឹក (AM)', 'Morning (AM)', '7:15:00', '11:00:00', 'no', '8:15:00', 'no', '2025-10-01 01:36:29', '2025-10-28 00:49:17'),
  (2, 'វេនរសៀល (PM)', 'Afternoon (PM)', '12:00:00', '18:00:00', 'no', '14:16:00', 'no', '2025-10-01 01:36:29', '2025-12-01 10:02:37')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `units` (32 rows)
INSERT INTO `units` (`id`, `name`, `created_at`, `updated_at`) VALUES
  (1, 'ប្រអប់', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (2, 'កេស', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (3, 'ក្បាល', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (4, 'ដុំ', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (5, 'ធុង', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (6, 'ឯកតា', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (7, 'ប្រអប់', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (8, 'កញ្ចប់', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (9, 'ញ៉ុង', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (10, 'កាបូប', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (11, 'ដប', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (12, 'កំប៉ុង', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (13, 'ការទុន', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (14, 'ប្រអប់ធំ', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (15, 'លីត្រ', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (16, 'មីលីលីត្រ', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (17, 'គីឡូក្រាម', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (18, 'ក្រាម', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (19, 'ម៉ែត្រ', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (20, 'សង់ទីម៉ែត្រ', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (21, 'ដុសិន', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (22, 'សំណុំ', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (23, 'គូ', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (24, 'មូល', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (25, 'មួក', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (26, 'រមៀល', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (27, 'ក្បាល', '2025-05-20 21:42:38', '2025-07-28 07:23:53'),
  (28, 'ឈុត', '2025-05-20 21:42:38', '2025-07-28 07:23:47'),
  (29, 'កញ្ចប់', '2025-05-20 21:42:38', '2025-07-28 07:23:57'),
  (30, 'បាច់ធំ', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (31, 'សន្លឹក', '2025-05-20 21:42:38', '2025-05-20 21:42:38'),
  (32, 'បំពង់', '2025-05-20 21:42:38', '2025-05-20 21:42:38')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `category` (4 rows)
INSERT INTO `category` (`id`, `category_name`, `noted`, `created_at`, `updated_at`) VALUES
  (1, 'សៀវភៅ', '', '2025-05-20 11:23:16', '2025-05-20 11:23:16'),
  (2, 'សម្លៀកបំពាក់', '', '2025-05-20 11:30:29', '2025-05-20 11:30:29'),
  (3, 'សម្ភារៈសិក្សា', '', '2025-05-20 11:30:49', '2025-05-20 11:30:49'),
  (4, 'ផ្សេងៗ​(Other)', '', '2025-06-20 13:12:55', '2025-06-24 09:11:17')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `items_group` (2 rows)
INSERT INTO `items_group` (`id`, `group_name`, `items_id`, `unit_id`, `created_at`, `updated_at`) VALUES
  (1, 'សៀវភៅមតេ្តយ្យសិក្សាកម្រិតខ្ពស់', '45,46', -1, '2025-07-09 11:07:07', '2025-07-09 11:07:07'),
  (2, 'សៀវភៅមតេ្តយ្យសិក្សាកម្រិតមធ្បម', '47,48', -1, '2025-07-09 11:11:29', '2025-07-09 11:11:29')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `leave_types` (5 rows)
INSERT INTO `leave_types` (`id`, `name`, `description`, `max_days_per_year`, `is_paid`, `requires_approval`, `created_at`, `updated_at`, `requires_proof`, `is_active`, `display_order`, `color_hex`, `max_days_per_month`) VALUES
  (1, 'Annual Leave', '', 0.0, 1, 1, '2026-07-02 19:32:06', '2026-09-02 09:40:01', 0, 1, 1, '#7C3AED', 1.0),
  (2, 'Sick Leave', '', 0.0, 1, 1, '2026-07-03 02:22:31', '2026-08-03 07:22:42', 1, 1, 2, '#42A5F5', NULL),
  (4, 'Marriage Leave', '', 0.0, 1, 1, '2026-07-03 02:24:05', '2026-08-03 07:22:54', 1, 1, 4, '#FFB300', NULL),
  (5, 'Dead leave or Funeral', '', 0.0, 1, 1, '2026-07-03 02:24:52', '2026-08-03 07:23:05', 0, 1, 5, '#E91E63', NULL),
  (9, 'Other leave', NULL, 10.0, 0, 1, '2026-08-21 02:24:23', '2026-08-24 08:20:03', 0, 1, 5, '#FFB300', NULL)
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `decimal_marks_allow` (4 rows)
INSERT INTO `decimal_marks_allow` (`id`, `program_id`, `allow`, `created_at`, `updated_at`) VALUES
  (1, 1, '0.25', '2025-12-10 06:45:03', '2025-12-10 06:45:03'),
  (2, 1, '0.50', '2025-12-10 06:45:03', '2025-12-10 06:45:03'),
  (3, 1, '0.75', '2025-12-10 06:45:03', '2025-12-10 06:45:03'),
  (4, 1, '0.00', '2025-12-16 02:38:49', '2025-12-16 02:38:49')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `market_categories` (5 rows)
INSERT INTO `market_categories` (`id`, `name`, `name_en`, `name_km`, `icon_key`, `sort_order`, `created_at`) VALUES
  (1, 'Books', 'Books', 'សៀវភៅ', 'books', 1, '2026-06-28 15:33:06'),
  (2, 'Uniform', 'Uniform', 'ឯកសណ្ឋាន', 'uniform', 2, '2026-06-28 15:33:06'),
  (3, 'Food', 'Food', 'អាហារ', 'food', 3, '2026-06-28 15:33:06'),
  (4, 'Electronics', 'Electronics', 'អេឡិចត្រូនិច', 'electronics', 4, '2026-06-28 15:33:06'),
  (5, 'Other', 'Other', 'ផ្សេងៗ', 'other', 99, '2026-06-28 15:33:06')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `market_settings` (1 rows)
INSERT INTO `market_settings` (`id`, `welcome_enabled`, `welcome_skip_seconds`, `welcome_version`, `updated_at`) VALUES
  (1, 0, 30, 1, '2026-07-23 15:04:43')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `app_branding_settings` (1 rows)
INSERT INTO `app_branding_settings` (`id`, `icon_name`, `top_text`, `bottom_text`, `icon_background_color`, `icon_color`, `top_text_color`, `bottom_text_color`, `created_at`, `updated_at`, `icon_background_color_dark`, `icon_color_dark`, `top_text_color_dark`, `bottom_text_color_dark`, `use_logo_image`, `logo_image_url`, `logo_image_url_dark`) VALUES
  (1, 'school_rounded', 'PAMA', 'INTERNATIONAL SCHOOL', '#1E5BD8', '#FFFFFF', '#22252A', '#6F7280', '2026-03-17 19:57:09', '2026-04-25 12:11:07', '#1E5BD8', '#FFFFFF', '#FFFFFF', '#B7C0D1', 1, '/uploads/branding/branding_logo_light_24700c3b24.jpg', '/uploads/branding/branding_logo_dark_7419206d06.jpg')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `app_quick_action_settings` (1 rows)
INSERT INTO `app_quick_action_settings` (`id`, `items_json`, `updated_at`) VALUES
  (1, '[{"id":"website_1784808728018332","kind":"website","title_en":"The One News","title_km":"The One News","title_zh":"","url":"https://theonenewsasia.com/","icon_name":"newspaper","color_hex":"#E11D48","visible":true,"sort_order":0,"open_mode":"embedded","highlight_new":true,"icon_image_url":""},{"id":"website_1784939001066138","kind":"website","title_en":"Facebook","title_km":"ហ្វេសបុក","title_zh":"","url":"https://www.facebook.com/share/1EZEcrB9LS/","icon_name":"school","color_hex":"#1677F2","visible":false,"sort_order":1,"open_mode":"embedded","highlight_new":true,"icon_image_url":""},{"id":"contact","kind":"contact","title_en":"Contact & map","title_km":"ទំនាក់ទំនង និងផែនទី","title_zh":"联系与地图","url":null,"icon_name":"contact_phone","color_hex":"#1677F2","visible":true,"sort_order":2,"open_mode":"embedded","highlight_new":false,"icon_image_url":""},{"id":"admissions","kind":"admissions","title_en":"Admissions","title_km":"ចុះឈ្មោះសិស្ស","title_zh":"招生","url":null,"icon_name":"assignment","color_hex":"#1677F2","visible":true,"sort_order":3,"open_mode":"embedded","highlight_new":false,"icon_image_url":""},{"id":"fees","kind":"fees","title_en":"Fees","title_km":"ថ្លៃសិក្សា","title_zh":"费用","url":null,"icon_name":"payments","color_hex":"#1677F2","visible":true,"sort_order":4,"open_mode":"embedded","highlight_new":false,"icon_image_url":""}]', '2026-07-25 00:58:23')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `attendance_system_settings` (1 rows)
INSERT INTO `attendance_system_settings` (`id`, `require_location`, `block_mock_location`, `block_developer_options`, `allowed_ip_ranges`, `allow_early_clock_in_mins`, `allow_late_clock_out_mins`, `late_grace_minutes`, `updated_at`, `created_at`, `per_session_early_clock_in_mins`, `min_minutes_before_checkout`, `allow_early_leave_mins`, `allow_makeup_missing_sessions`, `notify_enable_before`, `notify_minutes_before`, `notify_enable_after`, `notify_minutes_after`, `notify_enable_before_checkout`, `notify_minutes_before_checkout`, `notify_enable_after_checkout`, `notify_minutes_after_checkout`, `session_transition_wait_mins`) VALUES
  (1, 1, 1, 0, '', 120, 480, 15, '2026-09-11', '2026-01-09 04:29:31', '[190, 40]', 30, 0, 0, 1, '[10]', 1, '[5]', 0, '[0]', 1, '[5]', 10)
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `certificate_settings` (2 rows)
INSERT INTO `certificate_settings` (`id`, `academic_id`, `prefix`, `surfix`, `digit`, `year`, `created_at`, `updated_at`, `orientation`) VALUES
  (1, 1, '', '/25PAMAIS', 4, NULL, '2026-06-03 18:06:49', '2026-06-03 18:06:49', 'landscape'),
  (2, 2, '', '/26PAMAIS', 4, NULL, '2026-06-03 18:07:03', '2026-06-03 18:07:03', 'landscape')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `pickup_settings` (3 rows)
INSERT INTO `pickup_settings` (`id`, `academic_id`, `repeat_count`, `cooldown_seconds`, `calling_enabled`, `updated_at`) VALUES
  (1, 1, 2, 60, 1, '2026-07-08 04:36:40'),
  (9, 2, 3, 300, 0, '2026-07-20 08:26:53'),
  (10, 16, 3, 300, 0, '2026-09-01 10:02:16')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `price_visibility_settings` (1 rows)
INSERT INTO `price_visibility_settings` (`id`, `branch_id`, `program_id`, `show_monthly`, `show_quarter`, `show_semester`, `show_oneyear`, `created_at`, `updated_at`) VALUES
  (1, NULL, NULL, 1, 1, 1, 1, '2026-03-17 01:43:26', '2026-08-25 11:17:07')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `results_top_students_display_settings` (1 rows)
INSERT INTO `results_top_students_display_settings` (`id`, `avatar_chip_mode`, `hide_section`, `updated_at`, `hide_medals_section`) VALUES
  (1, 'grade', 0, '2026-07-25 00:21:56', 0)
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `medalname` (93 rows)
INSERT INTO `medalname` (`id`, `medal_name`, `created_at`, `updated_at`) VALUES
  (1, 'កម្មវិធីប៉ាម៉ា', '2025-07-25 13:04:17', '2025-07-25 13:04:17'),
  (2, 'ប្រកបពាក្យ និងអក្ខរវិញ្ញាស', '2025-07-25 13:04:17', '2025-07-28 02:40:46'),
  (3, 'អំណាន និងកំណាព្យ', '2025-07-28 02:35:26', '2025-07-28 02:35:26'),
  (4, 'ប្រកួតនិទានរឿង', '2025-07-28 02:35:56', '2025-07-28 02:35:56'),
  (5, 'បទបង្ហាញអមដោយរូបភាព', '2025-07-28 02:36:31', '2025-07-28 02:36:31'),
  (6, 'និយាយជាសាធារណៈ', '2025-07-28 02:37:10', '2025-07-28 02:37:10'),
  (7, 'តែងសេក្ដី', '2025-07-28 02:41:08', '2025-07-28 02:41:08'),
  (8, 'សិស្សឆ្នើម', '2025-07-28 02:41:25', '2025-07-28 02:41:25'),
  (9, 'Picture Prompts', '2025-07-28 02:43:26', '2025-08-28 03:29:50'),
  (10, 'Outstanding students', '2025-07-28 02:44:20', '2025-07-28 02:44:20'),
  (11, 'Story Telling', '2025-07-28 02:45:57', '2025-07-29 02:45:15'),
  (12, 'Show and Tell', '2025-07-28 02:46:25', '2025-07-28 02:46:25'),
  (13, 'Public Speaking', '2025-07-28 02:47:00', '2025-07-28 02:47:00'),
  (14, 'Reading Contest', '2025-07-28 02:47:18', '2025-07-29 09:36:07'),
  (17, 'ISOCSEA NR SCI', '2025-07-28 03:06:58', '2026-07-31 03:57:19'),
  (18, 'សំណេរ និងអត្ថន័យពាក្យ', '2025-07-28 03:14:16', '2025-07-28 03:14:16'),
  (19, 'ប្រកួតអំណាន និងស្មូត្រកំណាព្យ', '2025-07-28 03:14:23', '2025-07-28 03:14:23'),
  (20, 'IMOCSEA NR MATH', '2025-07-28 03:20:47', '2026-07-31 03:55:50'),
  (21, 'SMC', '2025-07-28 03:22:41', '2025-07-28 03:22:41'),
  (23, 'SEAMO', '2025-07-28 03:23:33', '2025-07-28 03:23:33'),
  (24, 'AMO', '2025-07-28 03:23:47', '2025-07-28 03:23:47'),
  (25, 'TEENEAGLE', '2025-07-28 03:24:10', '2025-07-28 03:24:10'),
  (26, 'TIMO', '2025-07-28 03:24:24', '2025-07-28 03:24:24'),
  (27, 'AMC FINAL', '2025-07-28 03:24:46', '2025-07-28 03:24:46'),
  (28, 'IGC', '2025-07-28 03:25:17', '2025-07-28 03:25:17'),
  (35, 'PIMSO NR MATH', '2025-07-28 03:32:34', '2026-07-31 06:36:42'),
  (36, 'PIMSO NR SCI', '2025-07-28 03:32:50', '2026-07-31 06:36:57'),
  (37, 'WMI', '2025-07-28 03:33:02', '2025-07-28 03:33:02'),
  (38, 'SASMO', '2025-07-28 03:33:13', '2025-07-28 03:33:13'),
  (39, 'BBB', '2025-07-28 03:33:42', '2025-07-28 03:33:42'),
  (42, 'IMEC', '2025-07-28 03:34:37', '2025-07-28 03:34:37'),
  (43, 'MPCH', '2025-07-28 03:34:50', '2025-07-28 03:34:50'),
  (44, 'BMC', '2025-07-28 03:35:02', '2025-07-28 03:35:02'),
  (46, 'Dream', '2025-08-13 03:35:24', '2025-08-13 03:35:24'),
  (48, 'CIMOC PRE', '2025-10-25 01:50:24', '2026-07-03 10:12:50'),
  (51, 'VIAMC', '2026-01-19 00:58:49', '2026-01-19 00:58:49'),
  (52, 'SEAMOX IR', '2026-01-26 02:44:38', '2026-07-31 06:46:11'),
  (53, 'BEBRAS', '2026-03-18 02:52:18', '2026-03-18 02:52:18'),
  (54, 'SIMSO/MATH', '2026-03-24 07:19:19', '2026-03-24 07:19:19'),
  (55, 'SIMSO/SCIENCE', '2026-03-24 07:19:50', '2026-03-24 07:19:50'),
  (57, 'WMC', '2026-04-21 07:29:48', '2026-04-21 07:29:48'),
  (58, 'WEC', '2026-04-21 07:30:51', '2026-04-21 07:30:51'),
  (59, 'Math Kangaroo', '2026-04-21 08:09:38', '2026-04-21 08:09:38'),
  (60, 'Romdul Scholars Challenge', '2026-05-18 02:44:21', '2026-06-10 02:20:31'),
  (61, 'WSC/Scholar\'s Bowl', '2026-06-01 06:53:33', '2026-06-01 06:53:33'),
  (62, 'WSC/Writing', '2026-06-01 06:54:30', '2026-06-01 06:54:30'),
  (63, 'WSC/Debate', '2026-06-01 06:56:18', '2026-06-01 06:56:18'),
  (64, 'WSC/Scholar\'s Challenge', '2026-06-01 06:57:07', '2026-06-01 06:57:07'),
  (65, 'WSC/TEAM WRITING', '2026-06-01 07:02:06', '2026-07-31 08:13:12'),
  (66, 'WSC/TEAM DEBATE', '2026-06-01 07:02:27', '2026-06-01 07:02:27'),
  (67, 'KOALA/ENGLISH', '2026-06-09 03:08:19', '2026-06-09 03:08:19'),
  (68, 'KOALA/MATH', '2026-06-09 03:08:42', '2026-06-09 03:08:42'),
  (69, 'KOALA/SCIENCE', '2026-06-09 03:09:10', '2026-06-09 03:09:10'),
  (70, 'KOALA/ARTS', '2026-06-09 03:09:22', '2026-06-09 03:11:43'),
  (71, 'IESO NR SCI', '2026-06-09 08:29:26', '2026-07-30 09:38:43'),
  (73, 'Linker Scientia Cup', '2026-06-13 01:24:55', '2026-06-13 01:24:55'),
  (74, 'Linker/Math', '2026-06-15 03:37:07', '2026-06-15 03:37:07'),
  (75, 'Linker/Bio', '2026-06-15 03:39:34', '2026-06-15 03:39:34'),
  (76, 'Linker/Chemistry', '2026-06-15 03:44:56', '2026-06-15 03:44:56'),
  (77, 'Linker/Physic', '2026-06-15 03:54:02', '2026-06-15 03:54:02'),
  (78, 'Romdul/Math', '2026-06-20 02:03:38', '2026-06-20 02:03:38'),
  (79, 'Romdul/science', '2026-06-20 02:04:15', '2026-06-20 02:04:15'),
  (80, 'Romdul/Geo', '2026-06-20 02:06:00', '2026-06-20 02:06:00'),
  (81, 'Romdul/History', '2026-06-20 02:06:22', '2026-06-20 02:06:22'),
  (82, 'Romdul/Art', '2026-06-20 02:06:37', '2026-06-20 02:06:37'),
  (83, 'CIMOC FINAL', '2026-07-03 10:26:37', '2026-07-03 10:26:37'),
  (85, 'PHIMO NR MATH', '2026-07-08 10:13:41', '2026-07-31 04:09:09'),
  (86, 'COPERNICUS MATH', '2026-07-09 08:42:48', '2026-07-09 08:42:48'),
  (90, 'GMC', '2026-07-09 08:47:04', '2026-07-09 08:47:04'),
  (91, 'IESO IR', '2026-07-09 08:49:15', '2026-07-30 09:36:03'),
  (92, 'PHIMO IR', '2026-07-09 08:52:19', '2026-07-31 04:08:06'),
  (93, 'SMGF', '2026-07-09 08:54:51', '2026-07-09 08:54:51'),
  (94, 'WSC IR SCI', '2026-07-09 08:58:11', '2026-07-31 08:09:44'),
  (95, 'ESB PRELIMINARY', '2026-07-09 09:45:48', '2026-07-09 09:45:48'),
  (96, 'ESB FINAL', '2026-07-09 09:46:13', '2026-07-09 09:46:13'),
  (97, 'FISO IR ARTS', '2026-07-30 08:08:51', '2026-07-30 08:08:51'),
  (98, 'FISO IR ENG', '2026-07-30 08:09:03', '2026-07-30 08:09:03'),
  (99, 'FISO IR IQ', '2026-07-30 08:09:16', '2026-07-30 08:09:16'),
  (100, 'FISO IR MATH', '2026-07-30 08:10:14', '2026-07-30 08:10:14'),
  (101, 'FISO IR SCI', '2026-07-30 08:10:19', '2026-07-30 08:10:19'),
  (102, 'FISO NR ART', '2026-07-30 08:10:46', '2026-07-30 08:10:46'),
  (103, 'FISO NR ENG', '2026-07-30 08:10:52', '2026-07-30 08:10:52'),
  (104, 'FISO NR IQ', '2026-07-30 08:10:58', '2026-07-30 08:10:58'),
  (105, 'FISO NR MATH', '2026-07-30 08:11:06', '2026-07-30 08:11:06'),
  (106, 'FISO NR SCI', '2026-07-30 08:11:12', '2026-07-30 08:11:12'),
  (107, 'FISO NR TECH', '2026-07-30 08:11:42', '2026-07-30 08:11:42'),
  (108, 'HKIMO IR', '2026-07-30 09:19:32', '2026-07-30 09:19:32'),
  (109, 'HKIMO NR', '2026-07-30 09:19:37', '2026-07-30 09:19:37'),
  (110, 'IEMO NR ENG', '2026-07-30 09:29:01', '2026-07-30 09:29:01'),
  (111, 'PIMSO IR MATH', '2026-07-31 06:37:05', '2026-07-31 06:37:05'),
  (112, 'PIMSO IR SCI', '2026-07-31 06:37:12', '2026-07-31 06:37:12'),
  (113, 'TIMO IR', '2026-07-31 07:58:34', '2026-07-31 07:58:34'),
  (114, 'VIAMC IR', '2026-07-31 08:00:36', '2026-07-31 08:00:36')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `medal_points_setup` (96 rows)
INSERT INTO `medal_points_setup` (`program_name`, `gold_pts`, `silver_pts`, `bronze_pts`, `diamond_pts`, `participation_pts`) VALUES
  ('AMC FINAL', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('AMO', 4.0, 3.0, 2.0, 0.0, 0.5),
  ('BBB', 5.0, 4.0, 3.0, 0.0, 1.0),
  ('BEBRAS', 5.0, 4.0, 3.0, 0.0, 0.0),
  ('BMC', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('CIMOC FINAL', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('CIMOC PRE', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('COPERNICUS MATH', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('Dream', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('ESB FINAL', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('ESB PRELIMINARY', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('FISO GR ENG', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('FISO GR MATH', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('FISO GR SCI', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('FISO IR ARTS', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('FISO IR ENG', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('FISO IR IQ', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('FISO IR MATH', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('FISO IR SCI', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('FISO NR ART', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('FISO NR ENG', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('FISO NR IQ', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('FISO NR MATH', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('FISO NR SCI', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('FISO NR TECH', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('GMC', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('HKIMO', 0.0, 0.0, 0.0, 0.0, 0.0),
  ('HKIMO IR', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('HKIMO NR', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('IEMO NR ENG', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('IESO IR', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('IESO NR SCI', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('IMOCSEA NR MATH', 4.0, 3.0, 2.0, 5.0, 1.0),
  ('ISOCSEA NR SCI', 4.0, 3.0, 2.0, 5.0, 1.0),
  ('KOALA/ARTS', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('KOALA/ENGLISH', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('KOALA/MATH', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('KOALA/SCIENCE', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('Linker Scientia Cup', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Linker/Bio', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Linker/Chemistry', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Linker/Math', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Linker/Physic', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Math Kangaroo', 3.0, 2.0, 1.0, 0.0, 0.5),
  ('MPCH', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Outstanding students', 3.0, 2.0, 1.0, 0.0, 0.0),
  ('PHIMO IR', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('PHIMO NR MATH', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('Picture Prompts', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('PIMSO IR MATH', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('PIMSO IR SCI', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('PIMSO NR MATH', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('PIMSO NR SCI', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('Public Speaking', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Reading Contest', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Romdul Scholars Challenge', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Romdul/Art', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Romdul/Geo', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Romdul/History', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Romdul/Math', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Romdul/science', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('SASMO', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('SEAMO', 4.0, 3.0, 2.0, 0.0, 0.5),
  ('SEAMOX IR', 7.0, 6.0, 5.0, 0.0, 3.0),
  ('Show and Tell', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('SIMSO/MATH', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('SIMSO/SCIENCE', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('SMC', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('SMGF', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('Spelling Bee', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('Story Telling', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('TEENEAGLE', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('TIMO', 4.0, 3.0, 2.0, 0.0, 1.0),
  ('TIMO IR', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('VIAMC', 4.0, 3.0, 2.0, 0.0, 0.5),
  ('VIAMC IR', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('WEC', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('WMC', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('WMI', 4.0, 3.0, 2.0, 0.0, 0.5),
  ('WSC IR SCI', 5.0, 4.0, 3.0, 0.0, 2.0),
  ('WSC/Debate', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('WSC/Scholar\'s Bowl', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('WSC/Scholar\'s Challenge', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('WSC/TEAM DEBATE', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('WSC/TEAM WRITING', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('WSC/Writing', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('កម្មវិធីប៉ាម៉ា', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('តែងសេក្ដី', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('និយាយជាសាធារណៈ', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('បទបង្ហាញអមដោយរូបភាព', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('ប្រកបពាក្យ និងអក្ខរវិញ្ញាស', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('ប្រកួតនិទានរឿង', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('ប្រកួតអំណាន និងស្មូត្រកំណាព្យ', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('សំណេរ និងអត្ថន័យពាក្យ', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('សិស្សឆ្នើម', 2.0, 1.0, 0.5, 0.0, 0.0),
  ('អំណាន និងកំណាព្យ', 2.0, 1.0, 0.5, 0.0, 0.0)
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `medal_price` (11 rows)
INSERT INTO `medal_price` (`id`, `name_us`, `name_kh`, `amount`, `academic_id`, `created_at`, `updated_at`) VALUES
  (1, 'Gold', 'មាស', '20.00', 1, '2025-07-25 13:34:45', '2025-07-25 13:34:45'),
  (2, 'Silver', 'ប្រាក់', '15.00', 1, '2025-07-25 13:34:45', '2025-07-25 13:34:45'),
  (3, 'Bronze', 'សំរិទ្ធ', '10.00', 1, '2025-07-25 13:35:37', '2025-07-25 13:35:37'),
  (4, 'Gold', 'មាស', '20.00', 2, '2025-08-27 01:59:57', '2025-08-27 01:59:57'),
  (5, 'Silver', 'ប្រាក់', '15.00', 2, '2025-08-27 02:00:21', '2025-08-27 02:00:21'),
  (6, 'Bronze', 'សំរិទ្ធ', '10.00', 2, '2025-08-27 02:00:50', '2025-08-27 02:00:50'),
  (7, 'Dimond', 'ពេជ្រ', '20.00', 2, '2025-11-12 06:45:16', '2025-11-12 06:45:16'),
  (8, 'Gold', 'មាស', '20.00', 16, '2026-09-09 06:47:59', '2026-09-09 06:47:59'),
  (9, 'Silver', 'ប្រាក់', '15.00', 16, '2026-09-09 06:47:59', '2026-09-09 06:47:59'),
  (10, 'Bronze', 'សំរិទ្ធ', '10.00', 16, '2026-09-09 06:47:59', '2026-09-09 06:47:59'),
  (11, 'Dimond', 'ពេជ្រ', '20.00', 16, '2026-09-09 06:47:59', '2026-09-09 06:47:59')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `nittes` (6 rows)
INSERT INTO `nittes` (`id`, `name_us`, `name_kh`, `created_at`, `updated_at`) VALUES
  (1, 'A', 'ល្អប្រសើរ', '2025-06-11 13:53:38', '2025-06-11 13:53:38'),
  (2, 'B', 'ល្អណាស់', '2025-06-11 13:53:38', '2025-06-11 13:53:38'),
  (3, 'C', 'ល្អ', '2025-06-11 13:54:33', '2025-06-11 13:54:33'),
  (4, 'D', 'បង្គួរ', '2025-06-11 13:54:33', '2025-06-11 13:54:33'),
  (5, 'E', 'មធ្យម', '2025-06-11 13:55:44', '2025-06-11 13:55:44'),
  (6, 'F', 'ក្រោមមធ្យម', '2025-06-11 13:55:44', '2025-06-11 13:55:44')
ON DUPLICATE KEY UPDATE id=id;

-- Default seed data for `nittes_discount` (6 rows)
INSERT INTO `nittes_discount` (`id`, `academic_id`, `branch_id`, `amount`, `nittes_id`, `created_at`, `updated_at`, `created_by`) VALUES
  (1, 1, 2, '20.00', 1, '2025-06-11 14:05:33', '2025-07-03 10:26:00', 58),
  (2, 1, 2, '15.00', 2, '2025-06-11 15:11:13', '2025-07-03 10:26:11', 58),
  (3, 1, 2, '10.00', 3, '2025-07-03 10:29:42', '2025-07-03 10:29:42', 58),
  (4, 1, 1, '20.00', 1, '2025-07-03 10:30:23', '2025-07-03 10:30:23', 58),
  (5, 1, 1, '15.00', 2, '2025-07-03 10:30:23', '2025-07-03 10:30:23', 58),
  (6, 1, 1, '10.00', 3, '2025-07-03 10:31:15', '2025-07-03 10:31:15', 58)
ON DUPLICATE KEY UPDATE id=id;

SET FOREIGN_KEY_CHECKS = 1;
