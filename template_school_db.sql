-- Kampul SIS default school template; generated, do not edit.
-- All starter rows come from defaults/kampul_sis.json (version 1).
-- One branch and academic year; unique Super Admin created at provisioning.
SET NAMES utf8mb4;
SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `_schema_patches`;
CREATE TABLE `_schema_patches` (
  `patch_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`patch_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `academic`;
CREATE TABLE `academic` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `academic_program_images`;
CREATE TABLE `academic_program_images` (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_id` int NOT NULL,
  `image_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `position` int DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `program_id` (`program_id`) USING BTREE,
  KEY `ix_academic_program_images_id` (`id`) USING BTREE,
  CONSTRAINT `academic_program_images_ibfk_1` FOREIGN KEY (`program_id`) REFERENCES `academic_programs` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `academic_programs`;
CREATE TABLE `academic_programs` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `accounts`;
CREATE TABLE `accounts` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `ad_clicks`;
CREATE TABLE `ad_clicks` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `admin_logs`;
CREATE TABLE `admin_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `action` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `details` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `timestamp` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_admin_logs_user` (`user_id`) USING BTREE,
  KEY `idx_admin_logs_action` (`action`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `ads`;
CREATE TABLE `ads` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `ai_conversations`;
CREATE TABLE `ai_conversations` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `ai_messages`;
CREATE TABLE `ai_messages` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `alembic_version`;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`version_num`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `app_admins`;
CREATE TABLE `app_admins` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `app_branding_settings`;
CREATE TABLE `app_branding_settings` (
  `id` int NOT NULL,
  `icon_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'school_rounded',
  `top_text` varchar(80) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'KAMPUL',
  `bottom_text` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'SIS',
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

DROP TABLE IF EXISTS `app_quick_action_settings`;
CREATE TABLE `app_quick_action_settings` (
  `id` int NOT NULL,
  `items_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance`;
CREATE TABLE `attendance` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance__allowed_branches`;
CREATE TABLE `attendance__allowed_branches` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_attendance__allowed_branches_branch_id` (`branch_id`) USING BTREE,
  KEY `ix_attendance__allowed_branches_user_id` (`user_id`) USING BTREE,
  KEY `ix_attendance__allowed_branches_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_audience_presets`;
CREATE TABLE `attendance_audience_presets` (
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

DROP TABLE IF EXISTS `attendance_audit_log`;
CREATE TABLE `attendance_audit_log` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_log`;
CREATE TABLE `attendance_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `scan_time` datetime NOT NULL,
  `scan_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'arrival',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_attendance_log_student_time` (`student_id`,`scan_time`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_primary_device_events`;
CREATE TABLE `attendance_primary_device_events` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_primary_devices`;
CREATE TABLE `attendance_primary_devices` (
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

DROP TABLE IF EXISTS `attendance_processing_rules`;
CREATE TABLE `attendance_processing_rules` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_records`;
CREATE TABLE `attendance_records` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_schedule_exception_enrollments`;
CREATE TABLE `attendance_schedule_exception_enrollments` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_schedule_exceptions`;
CREATE TABLE `attendance_schedule_exceptions` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_schedules`;
CREATE TABLE `attendance_schedules` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_statistics`;
CREATE TABLE `attendance_statistics` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_system_settings`;
CREATE TABLE `attendance_system_settings` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `attendance_user_assignments`;
CREATE TABLE `attendance_user_assignments` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `background_cards`;
CREATE TABLE `background_cards` (
  `id` int NOT NULL AUTO_INCREMENT,
  `front_image` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `back_image` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `card_model` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `background_cert`;
CREATE TABLE `background_cert` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `bonus_deduction_rules`;
CREATE TABLE `bonus_deduction_rules` (
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

DROP TABLE IF EXISTS `branch`;
CREATE TABLE `branch` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `branch_contacts`;
CREATE TABLE `branch_contacts` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `bus_assignment_assistants`;
CREATE TABLE `bus_assignment_assistants` (
  `id` int NOT NULL AUTO_INCREMENT,
  `assignment_id` int NOT NULL,
  `assistant_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `bus_assignments`;
CREATE TABLE `bus_assignments` (
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

DROP TABLE IF EXISTS `bus_attendance`;
CREATE TABLE `bus_attendance` (
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

DROP TABLE IF EXISTS `bus_maintenance`;
CREATE TABLE `bus_maintenance` (
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

DROP TABLE IF EXISTS `bus_routes`;
CREATE TABLE `bus_routes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_id` int NOT NULL,
  `route_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_time` time NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `bus_stop_prices`;
CREATE TABLE `bus_stop_prices` (
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

DROP TABLE IF EXISTS `bus_stops`;
CREATE TABLE `bus_stops` (
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

DROP TABLE IF EXISTS `bus_stu_inroll`;
CREATE TABLE `bus_stu_inroll` (
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

DROP TABLE IF EXISTS `buses`;
CREATE TABLE `buses` (
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

DROP TABLE IF EXISTS `category`;
CREATE TABLE `category` (
  `id` int NOT NULL AUTO_INCREMENT,
  `category_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `noted` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `certificate_settings`;
CREATE TABLE `certificate_settings` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `check_in_security_events`;
CREATE TABLE `check_in_security_events` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `class_teachers`;
CREATE TABLE `class_teachers` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `classes`;
CREATE TABLE `classes` (
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

DROP TABLE IF EXISTS `daily_attendance`;
CREATE TABLE `daily_attendance` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `decimal_marks_allow`;
CREATE TABLE `decimal_marks_allow` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `program_id` int unsigned NOT NULL,
  `allow` decimal(3,2) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_program_allow` (`program_id`,`allow`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `demo_cert`;
CREATE TABLE `demo_cert` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `department`;
CREATE TABLE `department` (
  `id` int NOT NULL AUTO_INCREMENT,
  `department` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `translate` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `departments`;
CREATE TABLE `departments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `department` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `translate` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_departments_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `device_tokens`;
CREATE TABLE `device_tokens` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `discount_childs`;
CREATE TABLE `discount_childs` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `discount_result`;
CREATE TABLE `discount_result` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `grade_scale_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `enrollments`;
CREATE TABLE `enrollments` (
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

DROP TABLE IF EXISTS `exam_calculate_sign`;
CREATE TABLE `exam_calculate_sign` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `exam_calculate_sign_subjects`;
CREATE TABLE `exam_calculate_sign_subjects` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_calculate_sign_id` int NOT NULL,
  `subject_id` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_sign_id` (`exam_calculate_sign_id`) USING BTREE,
  KEY `idx_subject_id` (`subject_id`) USING BTREE,
  CONSTRAINT `fk_sign_subjects_sign` FOREIGN KEY (`exam_calculate_sign_id`) REFERENCES `exam_calculate_sign` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `expense_categories`;
CREATE TABLE `expense_categories` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `is_active` tinyint(1) DEFAULT '1',
  `created_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `expenses`;
CREATE TABLE `expenses` (
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

DROP TABLE IF EXISTS `feature_locks`;
CREATE TABLE `feature_locks` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `fee_services`;
CREATE TABLE `fee_services` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `feedbacks`;
CREATE TABLE `feedbacks` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `form_field_options`;
CREATE TABLE `form_field_options` (
  `id` int NOT NULL AUTO_INCREMENT,
  `field_id` int NOT NULL,
  `label` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `order` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `field_id` (`field_id`) USING BTREE,
  KEY `ix_form_field_options_id` (`id`) USING BTREE,
  CONSTRAINT `form_field_options_ibfk_1` FOREIGN KEY (`field_id`) REFERENCES `form_fields` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `form_fields`;
CREATE TABLE `form_fields` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `form_submission_values`;
CREATE TABLE `form_submission_values` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `form_submissions`;
CREATE TABLE `form_submissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `form_id` int NOT NULL,
  `user_id` int NOT NULL,
  `user_type` enum('all','parents','students','teachers') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `submitted_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `form_id` (`form_id`) USING BTREE,
  KEY `ix_form_submissions_id` (`id`) USING BTREE,
  CONSTRAINT `form_submissions_ibfk_1` FOREIGN KEY (`form_id`) REFERENCES `forms` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `forms`;
CREATE TABLE `forms` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `grade`;
CREATE TABLE `grade` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `grade_group`;
CREATE TABLE `grade_group` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `grade_scale`;
CREATE TABLE `grade_scale` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `grade_type`;
CREATE TABLE `grade_type` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `holidays`;
CREATE TABLE `holidays` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `date` date NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `hot_event_impressions`;
CREATE TABLE `hot_event_impressions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `hot_event_id` int NOT NULL,
  `user_id` int NOT NULL,
  `impression_count` int NOT NULL,
  `last_viewed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_hot_event_impressions_user_id` (`user_id`) USING BTREE,
  KEY `ix_hot_event_impressions_hot_event_id` (`hot_event_id`) USING BTREE,
  KEY `ix_hot_event_impressions_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `hot_events`;
CREATE TABLE `hot_events` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `inventories`;
CREATE TABLE `inventories` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `invoice`;
CREATE TABLE `invoice` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `invoice_items`;
CREATE TABLE `invoice_items` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `items_group`;
CREATE TABLE `items_group` (
  `id` int NOT NULL AUTO_INCREMENT,
  `group_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `items_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `unit_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `learning`;
CREATE TABLE `learning` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `learning_class_schedules`;
CREATE TABLE `learning_class_schedules` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `learning_homework`;
CREATE TABLE `learning_homework` (
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

DROP TABLE IF EXISTS `learning_homework_attachments`;
CREATE TABLE `learning_homework_attachments` (
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

DROP TABLE IF EXISTS `learning_schedule_exceptions`;
CREATE TABLE `learning_schedule_exceptions` (
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

DROP TABLE IF EXISTS `learning_session_logs`;
CREATE TABLE `learning_session_logs` (
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

DROP TABLE IF EXISTS `learning_time_slot_scopes`;
CREATE TABLE `learning_time_slot_scopes` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `learning_time_slots`;
CREATE TABLE `learning_time_slots` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `leave_approvers`;
CREATE TABLE `leave_approvers` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `leave_balance_adjustments`;
CREATE TABLE `leave_balance_adjustments` (
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

DROP TABLE IF EXISTS `leave_balances`;
CREATE TABLE `leave_balances` (
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

DROP TABLE IF EXISTS `leave_histories`;
CREATE TABLE `leave_histories` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `leave_policies`;
CREATE TABLE `leave_policies` (
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

DROP TABLE IF EXISTS `leave_policy_leave_type_association`;
CREATE TABLE `leave_policy_leave_type_association` (
  `leave_policy_id` int NOT NULL,
  `leave_type_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`leave_policy_id`,`leave_type_id`) USING BTREE,
  KEY `leave_type_id` (`leave_type_id`) USING BTREE,
  CONSTRAINT `leave_policy_leave_type_association_ibfk_1` FOREIGN KEY (`leave_policy_id`) REFERENCES `leave_policies` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `leave_policy_leave_type_association_ibfk_2` FOREIGN KEY (`leave_type_id`) REFERENCES `leave_types` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `leave_request_days`;
CREATE TABLE `leave_request_days` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `leave_requests`;
CREATE TABLE `leave_requests` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `leave_type_allocations`;
CREATE TABLE `leave_type_allocations` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `leave_types`;
CREATE TABLE `leave_types` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `login_attempts`;
CREATE TABLE `login_attempts` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `logtransaction`;
CREATE TABLE `logtransaction` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `mark_entry_locks`;
CREATE TABLE `mark_entry_locks` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `mark_lock_attempts`;
CREATE TABLE `mark_lock_attempts` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `mark_lock_passcodes`;
CREATE TABLE `mark_lock_passcodes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `passcode_hash` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `user_id` (`user_id`) USING BTREE,
  KEY `idx_mark_lock_passcodes_user` (`user_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `market_categories`;
CREATE TABLE `market_categories` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `market_listing_broadcasts`;
CREATE TABLE `market_listing_broadcasts` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `market_listing_images`;
CREATE TABLE `market_listing_images` (
  `id` int NOT NULL AUTO_INCREMENT,
  `listing_id` int NOT NULL,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_market_listing_images_id` (`id`) USING BTREE,
  KEY `ix_market_listing_images_listing_id` (`listing_id`) USING BTREE,
  CONSTRAINT `market_listing_images_ibfk_1` FOREIGN KEY (`listing_id`) REFERENCES `market_listings` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `market_listings`;
CREATE TABLE `market_listings` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `market_orders`;
CREATE TABLE `market_orders` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `market_reviews`;
CREATE TABLE `market_reviews` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `market_seller_bans`;
CREATE TABLE `market_seller_bans` (
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

DROP TABLE IF EXISTS `market_settings`;
CREATE TABLE `market_settings` (
  `id` int NOT NULL,
  `welcome_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `welcome_skip_seconds` int NOT NULL DEFAULT '30',
  `welcome_version` int NOT NULL DEFAULT '1',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `market_stores`;
CREATE TABLE `market_stores` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `market_wishlists`;
CREATE TABLE `market_wishlists` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `marks_input`;
CREATE TABLE `marks_input` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `marks_monthly`;
CREATE TABLE `marks_monthly` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `marks_monthly_items`;
CREATE TABLE `marks_monthly_items` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `marks_semester`;
CREATE TABLE `marks_semester` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `marks_semester_monthlies`;
CREATE TABLE `marks_semester_monthlies` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `marks_system`;
CREATE TABLE `marks_system` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `marks_system_subjects`;
CREATE TABLE `marks_system_subjects` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `marks_yearly`;
CREATE TABLE `marks_yearly` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `marks_yearly_semesters`;
CREATE TABLE `marks_yearly_semesters` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `medal_points_setup`;
CREATE TABLE `medal_points_setup` (
  `program_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `gold_pts` double DEFAULT '0',
  `silver_pts` double DEFAULT '0',
  `bronze_pts` double DEFAULT '0',
  `diamond_pts` double DEFAULT '0',
  `participation_pts` double DEFAULT '0',
  PRIMARY KEY (`program_name`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `medal_price`;
CREATE TABLE `medal_price` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name_us` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_kh` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(65,2) NOT NULL,
  `academic_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `medalname`;
CREATE TABLE `medalname` (
  `id` int NOT NULL AUTO_INCREMENT,
  `medal_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `medals`;
CREATE TABLE `medals` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `message_group_bans`;
CREATE TABLE `message_group_bans` (
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

DROP TABLE IF EXISTS `message_group_members`;
CREATE TABLE `message_group_members` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `message_group_settings`;
CREATE TABLE `message_group_settings` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `message_groups`;
CREATE TABLE `message_groups` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `message_pinned`;
CREATE TABLE `message_pinned` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `message_reactions`;
CREATE TABLE `message_reactions` (
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

DROP TABLE IF EXISTS `messages`;
CREATE TABLE `messages` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `news`;
CREATE TABLE `news` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `news_images`;
CREATE TABLE `news_images` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `nittes`;
CREATE TABLE `nittes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name_us` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_kh` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `nittes_discount`;
CREATE TABLE `nittes_discount` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academic_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `amount` decimal(65,2) NOT NULL,
  `nittes_id` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` int NOT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `notifications`;
CREATE TABLE `notifications` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `otp_codes`;
CREATE TABLE `otp_codes` (
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

DROP TABLE IF EXISTS `parent_permission_interactions`;
CREATE TABLE `parent_permission_interactions` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `parent_registration_audit`;
CREATE TABLE `parent_registration_audit` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `parent_student_link_requests`;
CREATE TABLE `parent_student_link_requests` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `parents`;
CREATE TABLE `parents` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `partner_images`;
CREATE TABLE `partner_images` (
  `id` int NOT NULL AUTO_INCREMENT,
  `partner_id` int NOT NULL,
  `image_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `ix_partner_images_id` (`id`) USING BTREE,
  KEY `ix_partner_images_partner_id` (`partner_id`) USING BTREE,
  CONSTRAINT `partner_images_ibfk_1` FOREIGN KEY (`partner_id`) REFERENCES `partners` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `partners`;
CREATE TABLE `partners` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `permissions`;
CREATE TABLE `permissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `permission_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `permission_name` (`permission_name`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `pickup`;
CREATE TABLE `pickup` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `pickup_branch_calling`;
CREATE TABLE `pickup_branch_calling` (
  `academic_id` int NOT NULL,
  `branch_id` int NOT NULL,
  `calling_enabled` tinyint(1) NOT NULL DEFAULT '0',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`academic_id`,`branch_id`) USING BTREE,
  KEY `idx_pbc_academic` (`academic_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `pickup_requests`;
CREATE TABLE `pickup_requests` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `pickup_settings`;
CREATE TABLE `pickup_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `academic_id` int NOT NULL,
  `repeat_count` int NOT NULL,
  `cooldown_seconds` int NOT NULL,
  `calling_enabled` tinyint(1) NOT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `ix_pickup_settings_academic_id` (`academic_id`) USING BTREE,
  KEY `ix_pickup_settings_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `position`;
CREATE TABLE `position` (
  `id` int NOT NULL AUTO_INCREMENT,
  `position` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `translate` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `departmentId` int NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `price_list`;
CREATE TABLE `price_list` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `price_visibility_settings`;
CREATE TABLE `price_visibility_settings` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `profile_frame_history`;
CREATE TABLE `profile_frame_history` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `profile_frames`;
CREATE TABLE `profile_frames` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `program`;
CREATE TABLE `program` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `qrattendance`;
CREATE TABLE `qrattendance` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `results_top_students`;
CREATE TABLE `results_top_students` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `results_top_students_display_settings`;
CREATE TABLE `results_top_students_display_settings` (
  `id` int NOT NULL,
  `avatar_chip_mode` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `hide_section` tinyint(1) NOT NULL DEFAULT '0',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `hide_medals_section` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `role_permissions`;
CREATE TABLE `role_permissions` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `roles`;
CREATE TABLE `roles` (
  `id` int NOT NULL AUTO_INCREMENT,
  `role_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `salary_bonuses`;
CREATE TABLE `salary_bonuses` (
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

DROP TABLE IF EXISTS `salary_deductions`;
CREATE TABLE `salary_deductions` (
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

DROP TABLE IF EXISTS `salary_history`;
CREATE TABLE `salary_history` (
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

DROP TABLE IF EXISTS `scholarship`;
CREATE TABLE `scholarship` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `academic_id` int NOT NULL,
  `program_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `school_documents`;
CREATE TABLE `school_documents` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `school_events`;
CREATE TABLE `school_events` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `school_overviews`;
CREATE TABLE `school_overviews` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `settings`;
CREATE TABLE `settings` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `shift`;
CREATE TABLE `shift` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `smart_download_links`;
CREATE TABLE `smart_download_links` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `android_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `ios_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `ix_smart_download_links_code` (`code`) USING BTREE,
  KEY `ix_smart_download_links_id` (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `splash_ads`;
CREATE TABLE `splash_ads` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `status`;
CREATE TABLE `status` (
  `id` int NOT NULL AUTO_INCREMENT,
  `status` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `student_activity_logs`;
CREATE TABLE `student_activity_logs` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `student_profile_edit_requests`;
CREATE TABLE `student_profile_edit_requests` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `students`;
CREATE TABLE `students` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `subject_attendance`;
CREATE TABLE `subject_attendance` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `subject_grade_components`;
CREATE TABLE `subject_grade_components` (
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

DROP TABLE IF EXISTS `subject_grade_plans`;
CREATE TABLE `subject_grade_plans` (
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

DROP TABLE IF EXISTS `subject_grade_scores`;
CREATE TABLE `subject_grade_scores` (
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

DROP TABLE IF EXISTS `subjects`;
CREATE TABLE `subjects` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `subjects_group`;
CREATE TABLE `subjects_group` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `teachers`;
CREATE TABLE `teachers` (
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

DROP TABLE IF EXISTS `telegram_attendance_settings`;
CREATE TABLE `telegram_attendance_settings` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `telegram_bot_auth_codes`;
CREATE TABLE `telegram_bot_auth_codes` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `telegram_branch_notification_routes`;
CREATE TABLE `telegram_branch_notification_routes` (
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

DROP TABLE IF EXISTS `telegram_chat_moderation_settings`;
CREATE TABLE `telegram_chat_moderation_settings` (
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

DROP TABLE IF EXISTS `telegram_group_members`;
CREATE TABLE `telegram_group_members` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `telegram_group_reply_settings`;
CREATE TABLE `telegram_group_reply_settings` (
  `chat_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `features` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`chat_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `telegram_login_sessions`;
CREATE TABLE `telegram_login_sessions` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `telegram_moderation_events`;
CREATE TABLE `telegram_moderation_events` (
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

DROP TABLE IF EXISTS `telegram_moderation_quarantine_items`;
CREATE TABLE `telegram_moderation_quarantine_items` (
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

DROP TABLE IF EXISTS `telegram_otp_sessions`;
CREATE TABLE `telegram_otp_sessions` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `telegram_tracked_chats`;
CREATE TABLE `telegram_tracked_chats` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `telegram_webhook_events`;
CREATE TABLE `telegram_webhook_events` (
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

DROP TABLE IF EXISTS `units`;
CREATE TABLE `units` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(25) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `user_financials`;
CREATE TABLE `user_financials` (
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

DROP TABLE IF EXISTS `user_home_app_permissions`;
CREATE TABLE `user_home_app_permissions` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `user_sessions`;
CREATE TABLE `user_sessions` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `users_resource`;
CREATE TABLE `users_resource` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `users_social_links`;
CREATE TABLE `users_social_links` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `work_locations`;
CREATE TABLE `work_locations` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `ws_broadcast_queue`;
CREATE TABLE `ws_broadcast_queue` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `channel` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` json NOT NULL,
  `created_at` timestamp(3) NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_ws_channel_created` (`channel`,`created_at`) USING BTREE,
  KEY `idx_ws_created` (`created_at`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `zing_book_branch_limits`;
CREATE TABLE `zing_book_branch_limits` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `zing_book_support`;
CREATE TABLE `zing_book_support` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `zing_book_support_history`;
CREATE TABLE `zing_book_support_history` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `zing_books`;
CREATE TABLE `zing_books` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `zing_payment_methods`;
CREATE TABLE `zing_payment_methods` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `zing_survey_questions`;
CREATE TABLE `zing_survey_questions` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `zing_survey_responses`;
CREATE TABLE `zing_survey_responses` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `zing_surveys`;
CREATE TABLE `zing_surveys` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- academic: 1 rows
INSERT INTO `academic` (`id`, `academic_name`, `academic_us_name`, `academic_start`, `academic_end`, `quarter_one_start`, `quarter_one_end`, `quarter_two_start`, `quarter_two_end`, `quarter_three_start`, `quarter_three_end`, `quarter_four_start`, `quarter_four_end`, `semester_one_start`, `semester_one_end`, `semester_two_start`, `semester_two_end`, `status`, `isUsed`, `isUsed_at`) VALUES
(1, '២០២៦-២០២៧', '2026-2027', '2026-08-24', '2027-07-08', '2026-08-24', '2026-11-05', '2026-11-06', '2027-01-29', '2027-02-08', '2027-04-23', '2027-04-26', '2027-07-08', '2026-08-24', '2027-01-29', '2027-02-08', '2027-07-08', 1, 0, NULL);

-- accounts: 2 rows
INSERT INTO `accounts` (`id`, `account_name`, `account_number`, `qr_code`, `branch_id`, `academic_id`, `balance`, `currency`, `bank_name`, `created_by`, `updated_by`) VALUES
(1, 'Kampul SIS Cash USD', '000000001', '', 1, 1, '0.00', 'USD', 'Cash', 1, 1),
(2, 'Kampul SIS Cash KHR', '000000002', '', 1, 1, '0.00', 'KHR', 'Cash', 1, 1);

-- alembic_version: 1 rows
INSERT INTO `alembic_version` (`version_num`) VALUES
('0001_initial_migration');

-- app_branding_settings: 1 rows
INSERT INTO `app_branding_settings` (`id`, `icon_name`, `top_text`, `bottom_text`, `icon_background_color`, `icon_color`, `top_text_color`, `bottom_text_color`, `icon_background_color_dark`, `icon_color_dark`, `top_text_color_dark`, `bottom_text_color_dark`, `use_logo_image`, `logo_image_url`, `logo_image_url_dark`) VALUES
(1, 'school_rounded', 'KAMPUL', 'SIS', '#1E5BD8', '#FFFFFF', '#22252A', '#6F7280', '#1E5BD8', '#FFFFFF', '#FFFFFF', '#B7C0D1', 0, NULL, NULL);

-- app_quick_action_settings: 1 rows
INSERT INTO `app_quick_action_settings` (`id`, `items_json`) VALUES
(1, '[]');

-- branch: 1 rows
INSERT INTO `branch` (`id`, `branch_name`, `contact`, `address_khmer`, `address_english`, `email`, `website`, `id_prefix`, `id_start_number`, `id_digit`, `id_reset_option`, `report_time`, `users_id`, `report_weekend`, `report_status`, `invoice_prefix`, `invoice_digit`, `invoice_start_number`, `invoice_reset_december`, `vatin_number`, `receipt_digit`, `receipt_prefix`, `receipt_start_number`, `receipt_reset_option`, `receipt_header`, `image_header`, `director_kName`, `director_eName`, `director_signature`, `stamp`, `headTeacher_kName`, `headTeacher_eName`, `headTeacher_signature`, `app_display_name`, `app_branch_cover`, `app_branch_facebook_url`, `app_branch_telegram_url`, `app_branch_youtube_url`, `app_branch_tiktok_url`, `app_branch_google_map_url`, `map_latitude`, `map_longitude`, `open_at`, `close_at`, `pickup_radius_meters`, `image_header_path`, `director_signature_path`, `headTeacher_signature_path`, `stamp_path`, `signature_url`, `stamp_url`) VALUES
(1, 'Kampul SIS Main Branch', NULL, NULL, NULL, NULL, NULL, 'KMP-', 1, 6, 'auto', NULL, NULL, 'no', 'no', 'INV-', 6, 1, 0, NULL, 6, 'REC-', 1, 'auto', '', '', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Kampul SIS', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '07:00:00', '17:00:00', 100, NULL, NULL, NULL, NULL, NULL, NULL);

-- category: 4 rows
INSERT INTO `category` (`id`, `category_name`, `noted`) VALUES
(1, 'សៀវភៅ', ''),
(2, 'សម្លៀកបំពាក់', ''),
(3, 'សម្ភារៈសិក្សា', ''),
(4, 'ផ្សេងៗ​(Other)', '');

-- decimal_marks_allow: 4 rows
INSERT INTO `decimal_marks_allow` (`id`, `program_id`, `allow`) VALUES
(1, 1, '0.25'),
(2, 1, '0.50'),
(3, 1, '0.75'),
(4, 1, '0.00');

-- department: 9 rows
INSERT INTO `department` (`id`, `department`, `translate`, `code`) VALUES
(1, 'Board of Directors', 'ក្រុមប្រឹក្សាភិបាល', 'BDD'),
(2, 'Management Team', 'គណៈគ្រប់គ្រង', 'MTD'),
(3, 'Human Resource​ ', 'ផ្នែកធនធានមនុស្ស', 'HRD'),
(4, 'Administrative', 'ផ្នែករដ្ឋបាល', 'AD'),
(5, 'Financial', 'ផ្នែកហិរញ្ញវត្ថុ', 'FD'),
(6, 'Information Technology', 'ផ្នែកព័ត៌មានវិទ្យា', 'ITD'),
(7, 'Marketing', 'ផ្នែកទីផ្សារ', 'MD'),
(8, 'Full Time Academic', 'ផ្នែកសិក្សាធិការ (ពេញម៉ោង)', 'FTD'),
(9, 'Part Time Academic', 'ផ្នែកសិក្សាធិការ (ក្រៅម៉ោង)', 'PTD');

-- exam_calculate_sign: 80 rows
INSERT INTO `exam_calculate_sign` (`id`, `program_id`, `grade_group_id`, `academic_id`, `marks_system_id`, `result_name`, `formula_expression`, `sign_code`, `divide_by_multiplier`, `exam_type`, `is_active`) VALUES
(107, 1, 29, 1, 83, 'ប្រចាំ​ ខែកញ្ញា', 'exam_calculate_sign_subjects', 'MON1', '11.00', 'input', 1),
(108, 1, 29, 1, 84, 'ប្រចាំ​ ខែតុលា', 'exam_calculate_sign_subjects', 'MON2', '11.00', 'input', 1),
(109, 1, 29, 1, 85, 'ប្រចាំ​ ខែធ្នូ', 'exam_calculate_sign_subjects', 'MON4', '11.00', 'input', 1),
(110, 1, 29, 1, 86, 'ប្រចាំ ខែកុម្ភៈ', 'exam_calculate_sign_subjects', 'MON5', '11.00', 'input', 1),
(111, 1, 29, 1, 87, 'ប្រចាំ​ ខែមីនា', 'exam_calculate_sign_subjects', 'MON6', '11.00', 'input', 1),
(112, 1, 29, 1, 88, 'ប្រចាំ​ ខែមេសា', 'exam_calculate_sign_subjects', 'MON7', '11.00', 'input', 1),
(113, 1, 29, 1, 89, 'ប្រចាំ​ ខែវិច្ឆិកា', 'exam_calculate_sign_subjects', 'MON3', '11.00', 'input', 1),
(114, 1, 29, 1, 90, 'ប្រឡងឆមាសទី១', 'exam_calculate_sign_subjects', 'SEM1', '11.00', 'input', 1),
(115, 1, 29, 1, 91, 'ប្រឡងឆមាសទី២', 'exam_calculate_sign_subjects', 'SEM2', '11.00', 'input', 1),
(116, 1, 29, 1, 0, 'លទ្ធផលឆមាសទី១', '(MON1+MON2+MON3+MON4)+SEM1', 'RSEM1', '2.00', 'semester', 1),
(117, 1, 29, 1, 92, 'ប្រចាំ​ ខែឧសភា', 'exam_calculate_sign_subjects', 'MON8', '11.00', 'input', 1),
(118, 1, 29, 1, 0, 'លទ្ធផលឆមាសទី២', '(MON5+MON6+MON7+MON8)+SEM2', 'RSEM2', '2.00', 'semester', 1),
(119, 1, 29, 1, 0, 'លទ្ធផលប្រចាំឆ្នាំ', 'RSEM1+RSEM2', 'YEAR', '2.00', 'yearly', 1),
(120, 1, 28, 1, 93, 'ប្រចាំ​ ខែកញ្ញា', 'exam_calculate_sign_subjects', 'MON1', '6.00', 'input', 1),
(121, 1, 28, 1, 94, 'ប្រចាំ​ ខែតុលា', 'exam_calculate_sign_subjects', 'MON2', '6.00', 'input', 1),
(122, 1, 28, 1, 95, 'ប្រចាំ​ ខែវិច្ឆិកា', 'exam_calculate_sign_subjects', 'MON3', '6.00', 'input', 1),
(123, 1, 28, 1, 96, 'ប្រចាំ​ ខែធ្នូ', 'exam_calculate_sign_subjects', 'MON4', '6.00', 'input', 1),
(124, 1, 28, 1, 97, 'ប្រឡងឆមាសទី១', 'exam_calculate_sign_subjects', 'SEM1', '6.00', 'input', 1),
(125, 1, 28, 1, 98, 'ប្រចាំ​ ខែមីនា', 'exam_calculate_sign_subjects', 'MON6', '6.00', 'input', 1),
(126, 1, 28, 1, 99, 'ប្រចាំ​ ខែមេសា', 'exam_calculate_sign_subjects', 'MON7', '6.00', 'input', 1),
(127, 1, 28, 1, 100, 'ប្រចាំ​ ខែឧសភា', 'exam_calculate_sign_subjects', 'MON8', '6.00', 'input', 1),
(128, 1, 28, 1, 101, 'ប្រចាំ ខែកុម្ភៈ', 'exam_calculate_sign_subjects', 'MON5', '6.00', 'input', 1),
(129, 1, 28, 1, 102, 'ប្រឡងឆមាសទី២', 'exam_calculate_sign_subjects', 'SEM2', '6.00', 'input', 1),
(130, 1, 28, 1, 0, 'លទ្ធផលឆមាសទី១', '(MON1+MON2+MON3+MON4)+SEM1', 'RSEM1', '2.00', 'semester', 1),
(131, 1, 28, 1, 0, 'លទ្ធផលឆមាសទី២', '(MON5+MON6+MON7+MON8)+SEM2', 'RSEM2', '2.00', 'semester', 1),
(132, 1, 28, 1, 0, 'លទ្ធផលប្រចាំឆ្នាំ', 'RSEM1+RSEM2', 'YEAR', '2.00', 'yearly', 1),
(133, 1, 32, 1, 103, 'ប្រចាំ​ ខែកញ្ញា', 'exam_calculate_sign_subjects', 'MON1', '18.00', 'input', 1),
(134, 1, 32, 1, 104, 'ប្រចាំ​ ខែតុលា', 'exam_calculate_sign_subjects', 'MON2', '18.00', 'input', 1),
(135, 1, 32, 1, 105, 'ប្រចាំ​ ខែធ្នូ', 'exam_calculate_sign_subjects', 'MON4', '18.00', 'input', 1),
(136, 1, 32, 1, 106, 'ប្រចាំ ខែកុម្ភៈ', 'exam_calculate_sign_subjects', 'MON5', '18.00', 'input', 1),
(137, 1, 32, 1, 107, 'ប្រចាំ​ ខែមីនា', 'exam_calculate_sign_subjects', 'MON6', '18.00', 'input', 1),
(138, 1, 32, 1, 108, 'ប្រចាំ​ ខែមេសា', 'exam_calculate_sign_subjects', 'MON7', '18.00', 'input', 1),
(139, 1, 32, 1, 109, 'ប្រចាំ​ ខែវិច្ឆិកា', 'exam_calculate_sign_subjects', 'MON3', '18.00', 'input', 1),
(140, 1, 32, 1, 110, 'ប្រចាំ​ ខែឧសភា', 'exam_calculate_sign_subjects', 'MON8', '18.00', 'input', 1),
(141, 1, 32, 1, 111, 'ប្រឡងឆមាសទី១', 'exam_calculate_sign_subjects', 'SEM1', '18.00', 'input', 1),
(142, 1, 32, 1, 112, 'ប្រឡងឆមាសទី២', 'exam_calculate_sign_subjects', 'SEM2', '18.00', 'input', 1),
(143, 1, 32, 1, 0, 'លទ្ធផលឆមាសទី១', '(MON1+MON2+MON3+MON4)+SEM1', 'RSEM1', '2.00', 'semester', 1),
(144, 1, 32, 1, 0, 'លទ្ធផលឆមាសទី២', '(MON5+MON6+MON7+MON8)+SEM2', 'RSEM2', '2.00', 'semester', 1),
(145, 1, 32, 1, 0, 'លទ្ធផលប្រចាំឆ្នាំ', 'RSEM1+RSEM2', 'YEAR', '2.00', 'yearly', 1),
(146, 3, 33, 1, 113, 'Mid- 1st Quarter', 'exam_calculate_sign_subjects', 'MON1', '7.00', 'input', 1),
(147, 3, 33, 1, 114, 'Final- 1st Quarter', 'exam_calculate_sign_subjects', 'MON2', '7.00', 'input', 1),
(148, 3, 33, 1, 115, 'Mid- 2nd Quarter', 'exam_calculate_sign_subjects', 'MON3', '7.00', 'input', 1),
(149, 3, 33, 1, 116, 'Final- 2nd Quarter', 'exam_calculate_sign_subjects', 'MON4', '7.00', 'input', 1),
(150, 3, 33, 1, 117, 'Mid- 3rd Quarter', 'exam_calculate_sign_subjects', 'MON5', '7.00', 'input', 1),
(151, 3, 33, 1, 118, 'Final- 3rd Quarter', 'exam_calculate_sign_subjects', 'MON6', '7.00', 'input', 1),
(152, 3, 33, 1, 119, 'Mid- 4th Quarter', 'exam_calculate_sign_subjects', 'MON7', '7.00', 'input', 1),
(153, 3, 33, 1, 120, 'Final- 4th Quarter', 'exam_calculate_sign_subjects', 'MON8', '7.00', 'input', 1),
(154, 3, 33, 1, 0, 'Semester I', 'MON1+MON2+MON3+MON4', 'RSEM1', '4.00', 'semester', 1),
(155, 3, 33, 1, 0, 'Semester II', 'MON5+MON6+MON7+MON8', 'RSEM2', '4.00', 'semester', 1),
(156, 3, 33, 1, 0, 'Yearly', 'RSEM1+RSEM2', 'YEAR', '2.00', 'yearly', 1),
(157, 2, 36, 1, 121, 'Mid- 1st Quarter', '38+39+40+41+42+43+44', 'MON1', '7.00', 'input', 1),
(158, 2, 36, 1, 122, 'Final- 1st Quarter', '38+39+40+41+42+43+44', 'MON2', '7.00', 'input', 1),
(159, 2, 36, 1, 123, 'Mid- 2nd Quarter', '38+39+40+41+42+43+44', 'MON3', '7.00', 'input', 1),
(160, 2, 36, 1, 124, 'Final- 2nd Quarter', '38+39+40+41+42+43+44', 'MON4', '7.00', 'input', 1),
(161, 2, 36, 1, 125, 'Mid- 3rd Quarter', '38+39+40+41+42+43+44', 'MON5', '7.00', 'input', 1),
(162, 2, 36, 1, 126, 'Final- 3rd Quarter', '38+39+40+41+42+43+44', 'MON6', '7.00', 'input', 1),
(163, 2, 36, 1, 127, 'Mid- 4th Quarter', '38+39+40+41+42+43+44', 'MON7', '7.00', 'input', 1),
(164, 2, 36, 1, 128, 'Final- 4th Quarter', '38+39+40+41+42+43+44', 'MON8', '7.00', 'input', 1),
(165, 2, 36, 1, 0, 'Semester I', 'MON1+MON2+MON3+MON4', 'RSEM1', '4.00', 'semester', 1),
(166, 2, 36, 1, 0, 'Semester II', 'MON5+MON6+MON7+MON8', 'RSEM2', '4.00', 'semester', 1),
(167, 2, 34, 1, 129, 'Mid- 1st Quarter', '38+39+40+41+42+43+44', 'MON1', '7.00', 'input', 1),
(168, 2, 34, 1, 130, 'Final- 1st Quarter', '38+39+40+41+42+43+44', 'MON2', '7.00', 'input', 1),
(169, 2, 34, 1, 131, 'Mid- 2nd Quarter', '38+39+40+41+42+43+44', 'MON3', '7.00', 'input', 1),
(170, 2, 34, 1, 132, 'Final- 2nd Quarter', '38+39+40+41+42+43+44', 'MON4', '7.00', 'input', 1),
(171, 2, 34, 1, 133, 'Mid- 3rd Quarter', '38+39+40+41+42+43+44', 'MON5', '7.00', 'input', 1),
(172, 2, 34, 1, 134, 'Final- 3rd Quarter', '38+39+40+41+42+43+44', 'MON6', '7.00', 'input', 1),
(173, 2, 34, 1, 135, 'Mid- 4th Quarter', '38+39+40+41+42+43+44', 'MON7', '7.00', 'input', 1),
(174, 2, 34, 1, 136, 'Final- 4th Quarter', '38+39+40+41+42+43+44', 'MON8', '7.00', 'input', 1),
(175, 2, 34, 1, 0, 'Semester I', 'MON1+MON2+MON3+MON4', 'RSEM1', '4.00', 'semester', 1),
(176, 2, 34, 1, 0, 'Semester II', 'MON5+MON6+MON7+MON8', 'RSEM2', '4.00', 'semester', 1),
(177, 2, 35, 1, 137, 'Mid- 1st Quarter', '38+39+40+41+42+43+44', 'MON1', '7.00', 'input', 1),
(178, 2, 35, 1, 138, 'Final- 1st Quarter', '38+39+40+41+42+43+44', 'MON2', '7.00', 'input', 1),
(179, 2, 35, 1, 139, 'Mid- 2nd Quarter', '38+39+40+41+42+43+44', 'MON3', '7.00', 'input', 1),
(180, 2, 35, 1, 140, 'Final- 2nd Quarter', '38+39+40+41+42+43+44', 'MON4', '7.00', 'input', 1),
(181, 2, 35, 1, 141, 'Mid- 3rd Quarter', '38+39+40+41+42+43+44', 'MON5', '7.00', 'input', 1),
(182, 2, 35, 1, 142, 'Final- 3rd Quarter', '38+39+40+41+42+43+44', 'MON6', '7.00', 'input', 1),
(183, 2, 35, 1, 143, 'Mid- 4th Quarter', '38+39+40+41+42+43+44', 'MON7', '7.00', 'input', 1),
(184, 2, 35, 1, 144, 'Final- 4th Quarter', '38+39+40+41+42+43+44', 'MON8', '7.00', 'input', 1),
(185, 2, 35, 1, 0, 'Semester I', 'MON1+MON2+MON3+MON4', 'RSEM1', '4.00', 'semester', 1),
(186, 2, 35, 1, 0, 'Semester II', 'MON5+MON6+MON7+MON8', 'RSEM2', '4.00', 'semester', 1);

-- exam_calculate_sign_subjects: 185 rows
INSERT INTO `exam_calculate_sign_subjects` (`id`, `exam_calculate_sign_id`, `subject_id`) VALUES
(2245, 116, 1),
(2246, 116, 1),
(2247, 116, 2),
(2248, 116, 3),
(2249, 116, 4),
(2250, 118, 2),
(2251, 118, 5),
(2252, 118, 6),
(2253, 118, 7),
(2254, 118, 8),
(2255, 119, 1),
(2256, 119, 2),
(2257, 143, 1),
(2258, 143, 1),
(2259, 143, 3),
(2260, 144, 7),
(2261, 145, 1),
(2262, 157, 38),
(2263, 157, 39),
(2264, 157, 40),
(2265, 157, 41),
(2266, 157, 42),
(2267, 157, 43),
(2268, 157, 44),
(2269, 158, 38),
(2270, 158, 39),
(2271, 158, 40),
(2272, 158, 41),
(2273, 158, 42),
(2274, 158, 43),
(2275, 158, 44),
(2276, 159, 38),
(2277, 159, 39),
(2278, 159, 40),
(2279, 159, 41),
(2280, 159, 42),
(2281, 159, 43),
(2282, 159, 44),
(2283, 160, 38),
(2284, 160, 39),
(2285, 160, 40),
(2286, 160, 41),
(2287, 160, 42),
(2288, 160, 43),
(2289, 160, 44),
(2290, 161, 38),
(2291, 161, 39),
(2292, 161, 40),
(2293, 161, 41),
(2294, 161, 42),
(2295, 161, 43),
(2296, 161, 44),
(2297, 162, 38),
(2298, 162, 39),
(2299, 162, 40),
(2300, 162, 41),
(2301, 162, 42),
(2302, 162, 43),
(2303, 162, 44),
(2304, 163, 38),
(2305, 163, 39),
(2306, 163, 40),
(2307, 163, 41),
(2308, 163, 42),
(2309, 163, 43),
(2310, 163, 44),
(2311, 164, 38),
(2312, 164, 39),
(2313, 164, 40),
(2314, 164, 41),
(2315, 164, 42),
(2316, 164, 43),
(2317, 164, 44),
(2318, 167, 38),
(2319, 167, 39),
(2320, 167, 40),
(2321, 167, 41),
(2322, 167, 42),
(2323, 167, 43),
(2324, 167, 44),
(2325, 168, 38),
(2326, 168, 39),
(2327, 168, 40),
(2328, 168, 41),
(2329, 168, 42),
(2330, 168, 43),
(2331, 168, 44),
(2332, 169, 38),
(2333, 169, 39),
(2334, 169, 40),
(2335, 169, 41),
(2336, 169, 42),
(2337, 169, 43),
(2338, 169, 44),
(2339, 170, 38),
(2340, 170, 39),
(2341, 170, 40),
(2342, 170, 41),
(2343, 170, 42),
(2344, 170, 43);
INSERT INTO `exam_calculate_sign_subjects` (`id`, `exam_calculate_sign_id`, `subject_id`) VALUES
(2345, 170, 44),
(2346, 171, 38),
(2347, 171, 39),
(2348, 171, 40),
(2349, 171, 41),
(2350, 171, 42),
(2351, 171, 43),
(2352, 171, 44),
(2353, 172, 38),
(2354, 172, 39),
(2355, 172, 40),
(2356, 172, 41),
(2357, 172, 42),
(2358, 172, 43),
(2359, 172, 44),
(2360, 173, 38),
(2361, 173, 39),
(2362, 173, 40),
(2363, 173, 41),
(2364, 173, 42),
(2365, 173, 43),
(2366, 173, 44),
(2367, 174, 38),
(2368, 174, 39),
(2369, 174, 40),
(2370, 174, 41),
(2371, 174, 42),
(2372, 174, 43),
(2373, 174, 44),
(2374, 177, 38),
(2375, 177, 39),
(2376, 177, 40),
(2377, 177, 41),
(2378, 177, 42),
(2379, 177, 43),
(2380, 177, 44),
(2381, 178, 38),
(2382, 178, 39),
(2383, 178, 40),
(2384, 178, 41),
(2385, 178, 42),
(2386, 178, 43),
(2387, 178, 44),
(2388, 179, 38),
(2389, 179, 39),
(2390, 179, 40),
(2391, 179, 41),
(2392, 179, 42),
(2393, 179, 43),
(2394, 179, 44),
(2395, 180, 38),
(2396, 180, 39),
(2397, 180, 40),
(2398, 180, 41),
(2399, 180, 42),
(2400, 180, 43),
(2401, 180, 44),
(2402, 181, 38),
(2403, 181, 39),
(2404, 181, 40),
(2405, 181, 41),
(2406, 181, 42),
(2407, 181, 43),
(2408, 181, 44),
(2409, 182, 38),
(2410, 182, 39),
(2411, 182, 40),
(2412, 182, 41),
(2413, 182, 42),
(2414, 182, 43),
(2415, 182, 44),
(2416, 183, 38),
(2417, 183, 39),
(2418, 183, 40),
(2419, 183, 41),
(2420, 183, 42),
(2421, 183, 43),
(2422, 183, 44),
(2423, 184, 38),
(2424, 184, 39),
(2425, 184, 40),
(2426, 184, 41),
(2427, 184, 42),
(2428, 184, 43),
(2429, 184, 44);

-- feature_locks: 15 rows
INSERT INTO `feature_locks` (`id`, `feature_id`, `feature_name`, `is_locked`, `locked_by`, `locked_at`, `created_at`) VALUES
(1, 'attendance_security', 'Attendance Security', 0, NULL, NULL, '2026-01-01 00:00:00'),
(2, 'work_locations', 'Work Locations', 0, NULL, NULL, '2026-01-01 00:00:00'),
(3, 'telegram_notifications', 'Telegram Notifications', 0, NULL, NULL, '2026-01-01 00:00:00'),
(4, 'company_settings', 'Company Settings', 0, NULL, NULL, '2026-01-01 00:00:00'),
(5, 'app_branding', 'App Branding', 0, NULL, NULL, '2026-01-01 00:00:00'),
(6, 'hot_events', 'Hot Events', 0, NULL, NULL, '2026-01-01 00:00:00'),
(7, 'manage_branches', 'Manage Branches', 0, NULL, NULL, '2026-01-01 00:00:00'),
(8, 'attendance_reports', 'Attendance Reports', 0, NULL, NULL, '2026-01-01 00:00:00'),
(9, 'manage_forms', 'Manage Forms', 0, NULL, NULL, '2026-01-01 00:00:00'),
(10, 'payroll_dashboard', 'Payroll Dashboard', 0, NULL, NULL, '2026-01-01 00:00:00'),
(11, 'academic_programs', 'Academic Programs', 0, NULL, NULL, '2026-01-01 00:00:00'),
(12, 'leave_setup', 'Leave Setup', 0, NULL, NULL, '2026-01-01 00:00:00'),
(13, 'leave_approvers', 'Leave Approvers', 0, NULL, NULL, '2026-01-01 00:00:00'),
(14, 'certificate_management', 'Certificate Management', 0, NULL, NULL, '2026-01-01 00:00:00'),
(15, 'attendance_settings', 'Attendance Settings', 0, NULL, NULL, '2026-01-01 00:00:00');

-- grade: 17 rows
INSERT INTO `grade` (`id`, `grade_name`, `grade_name_us`, `grade_type_id`, `group_Id`, `program_id`, `branch_id`, `academic_id`, `noted`, `updated_by`, `created_by`, `created_at`) VALUES
(128, 'មត្តេយ្យទាប', 'Kindergarten I', '69,70,72,73', 28, 1, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(129, 'មត្តេយ្យមធ្យម', 'Kindergarten II', '69,70,72,73', 28, 1, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(130, 'មត្តេយ្យខ្ពស់', 'Kindergarten III', '69,70,72,73', 28, 1, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(132, 'ថ្នាក់ទី១', 'Level 1', '69,70,72,73', 29, 1, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(133, 'ថ្នាក់ទី២', 'Level 2', '69,70,72,73', 29, 1, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(134, 'ថ្នាក់ទី៣', 'Level 3', '69,70,72,73', 29, 1, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(135, 'ថ្នាក់ទី៤', 'Level 4', '69,70,72,73', 29, 1, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(136, 'ថ្នាក់ទី៥', 'Level 5', '69,70,72,73', 29, 1, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(137, 'ថ្នាក់ទី៦', 'Level 6', '69,70,72,73', 29, 1, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(138, 'Pre-Primary', 'Pre-Primary', '81,84,82,85', 34, 2, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(139, 'Year 1', 'ថ្នាក់ទី១', '81,84,82,83,85,86', 35, 2, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(140, 'Year 2', 'ថ្នាក់ទី២', '81,84,82,83,85,86', 35, 2, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(141, 'Year 3', 'ថ្នាក់ទី៣', '81,84,82,83,85,86', 35, 2, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(142, 'Year 4', 'ថ្នាក់ទី៤', '81,84,82,83,85,86', 35, 2, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(143, 'Year 5', 'ថ្នាក់ទី៥', '81,84,82,83,85,86', 35, 2, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(144, 'Kindergarten I', 'មត្តេយ្យទាប', '75,76,78,79', 33, 3, 1, 1, '', 1, 1, '2026-01-01 00:00:00'),
(145, 'Kindergarten II', 'មត្តេយ្យមធ្យម', '75,76,78,79', 33, 3, 1, 1, '', 1, 1, '2026-01-01 00:00:00');

-- grade_group: 9 rows
INSERT INTO `grade_group` (`id`, `group_name`, `academic_id`, `program_id`, `multiplier`, `model_cer`, `noted`, `updated_by`, `created_by`, `created_at`, `updated_at`) VALUES
(28, 'មត្តេយ្យសិក្សា', 1, 1, '6.00', 1, '', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(29, 'បឋមសិក្សា', 1, 1, '11.00', 1, '', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(30, 'អនុវិទ្យាល័យ', 1, 1, '18.00', 1, '', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(31, 'អនុវិទ្យាល័យ ថ្នាក់ទី៩', 1, 1, '8.40', 1, '', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(32, 'វិទ្យាល័យ', 1, 1, '17.00', 1, '', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(33, 'Kindergarten', 1, 3, '7.00', 1, '', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(34, 'Primary', 1, 2, '7.00', 1, '', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(35, 'Secondary', 1, 2, '7.00', 1, '', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(36, 'High School', 1, 2, '7.00', 1, '', 1, 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00');

-- grade_scale: 50 rows
INSERT INTO `grade_scale` (`id`, `grade_group_id`, `academic_id`, `min_marks`, `max_marks`, `us_grade`, `nittes_id`, `scale_discount`, `kh_grade`, `is_overall`) VALUES
(80, 36, 1, '0.00', '49.99', 'E', NULL, NULL, 'Very low', 0),
(81, 36, 1, '50.00', '59.99', 'D', NULL, NULL, 'Limited', 0),
(82, 36, 1, '60.00', '79.99', 'C', NULL, NULL, 'Satisfactory', 0),
(83, 36, 1, '80.00', '89.99', 'B', NULL, NULL, 'High', 0),
(84, 36, 1, '90.00', '100.00', 'A', NULL, NULL, 'Excelent', 0),
(85, 33, 1, '0.00', '49.99', 'E', NULL, NULL, 'Very low', 0),
(86, 33, 1, '50.00', '59.99', 'D', NULL, NULL, 'Limited', 0),
(87, 33, 1, '60.00', '79.99', 'C', NULL, NULL, 'Satisfactory', 0),
(88, 33, 1, '80.00', '89.99', 'B', NULL, NULL, 'High', 0),
(89, 33, 1, '90.00', '100.00', 'A', NULL, NULL, 'Excelent', 0),
(90, 34, 1, '0.00', '49.99', 'E', NULL, NULL, 'Very low', 0),
(91, 34, 1, '50.00', '59.99', 'D', NULL, NULL, 'Limited', 0),
(92, 34, 1, '60.00', '79.99', 'C', NULL, NULL, 'Satisfactory', 0),
(93, 34, 1, '80.00', '89.99', 'B', NULL, NULL, 'High', 0),
(94, 34, 1, '90.00', '100.00', 'A', NULL, NULL, 'Excelent', 0),
(95, 35, 1, '90.00', '100.00', 'A', NULL, NULL, 'Excelent', 0),
(96, 35, 1, '80.00', '89.99', 'B', NULL, NULL, 'High', 0),
(97, 35, 1, '60.00', '79.99', 'C', NULL, NULL, 'Satisfactory', 0),
(98, 35, 1, '50.00', '59.99', 'D', NULL, NULL, 'Limited', 0),
(99, 35, 1, '0.00', '49.99', 'E', NULL, NULL, 'Very low', 0),
(100, 29, 1, '6.00', '6.99', 'D', NULL, NULL, 'បង្គួរ', 0),
(101, 29, 1, '9.00', '10.00', 'A', NULL, NULL, 'ល្អប្រសើរ', 0),
(102, 29, 1, '8.00', '8.99', 'B', NULL, NULL, 'ល្អណាស់', 0),
(103, 29, 1, '7.00', '7.99', 'C', NULL, NULL, 'ល្អ', 0),
(104, 29, 1, '5.00', '5.99', 'E', NULL, NULL, 'មធ្យម', 0),
(105, 29, 1, '0.00', '4.99', 'F', NULL, NULL, 'ក្រោមមធ្យម', 0),
(106, 28, 1, '90.00', '100.00', 'A', NULL, NULL, 'ល្អប្រសើរ', 0),
(107, 28, 1, '80.00', '89.99', 'B', NULL, NULL, 'ល្អណាស់', 0),
(108, 28, 1, '70.00', '79.99', 'C', NULL, NULL, 'ល្អ', 0),
(109, 28, 1, '60.00', '69.99', 'D', NULL, NULL, 'បង្គួរ', 0),
(110, 28, 1, '50.00', '59.99', 'E', NULL, NULL, 'មធ្យម', 0),
(111, 28, 1, '0.00', '49.99', 'F', NULL, NULL, 'ក្រោមមធ្យម', 0),
(112, 32, 1, '25.00', '29.99', 'E', NULL, NULL, 'មធ្យម', 0),
(113, 32, 1, '0.00', '24.99', 'F', NULL, NULL, 'ក្រោមមធ្យម', 0),
(114, 32, 1, '30.00', '34.99', 'D', NULL, NULL, 'បង្គួរ', 0),
(115, 32, 1, '35.00', '39.99', 'C', NULL, NULL, 'ល្អ', 0),
(116, 32, 1, '40.00', '44.99', 'B', NULL, NULL, 'ល្អណាស់', 0),
(117, 32, 1, '45.00', '50.00', 'A', NULL, NULL, 'ល្អប្រសើរ', 0),
(118, 30, 1, '45.00', '50.00', 'A', NULL, NULL, 'ល្អប្រសើរ', 0),
(119, 30, 1, '40.00', '44.99', 'B', NULL, NULL, 'ល្អណាស់', 0),
(120, 30, 1, '35.00', '39.99', 'C', NULL, NULL, 'ល្អ', 0),
(121, 30, 1, '30.00', '34.99', 'D', NULL, NULL, 'បង្គួរ', 0),
(122, 30, 1, '25.00', '29.99', 'E', NULL, NULL, 'មធ្យម', 0),
(123, 30, 1, '0.00', '24.99', 'F', NULL, NULL, 'ក្រោមមធ្យម', 0),
(124, 31, 1, '45.00', '50.00', 'A', NULL, NULL, 'ល្អប្រសើរ', 0),
(125, 31, 1, '40.00', '44.99', 'B', NULL, NULL, 'ល្អណាស់', 0),
(126, 31, 1, '35.00', '39.99', 'C', NULL, NULL, 'ល្អ', 0),
(127, 31, 1, '30.00', '34.99', 'D', NULL, NULL, 'បង្គួរ', 0),
(128, 31, 1, '0.00', '24.99', 'F', NULL, NULL, 'ក្រោមមធ្យម', 0),
(129, 31, 1, '25.00', '29.99', 'E', NULL, NULL, 'មធ្យម', 0);

-- grade_type: 18 rows
INSERT INTO `grade_type` (`id`, `type_name`, `program_id`, `branch_id`, `academic_id`, `shift_id`, `noted`, `created_by`, `updated_by`) VALUES
(69, 'ក១', 1, 1, 1, 1, NULL, 1, 1),
(70, 'ក២', 1, 1, 1, 1, NULL, 1, 1),
(71, 'ក៣', 1, 1, 1, 1, NULL, 1, 1),
(72, 'ខ១', 1, 1, 1, 2, NULL, 1, 1),
(73, 'ខ២', 1, 1, 1, 2, NULL, 1, 1),
(74, 'ខ៣', 1, 1, 1, 2, NULL, 1, 1),
(75, 'A1', 3, 1, 1, 1, NULL, 1, 1),
(76, 'A2', 3, 1, 1, 1, NULL, 1, 1),
(77, 'A3', 3, 1, 1, 1, NULL, 1, 1),
(78, 'B1', 3, 1, 1, 2, NULL, 1, 1),
(79, 'B2', 3, 1, 1, 2, NULL, 1, 1),
(80, 'B3', 3, 1, 1, 2, NULL, 1, 1),
(81, 'A1', 2, 1, 1, 1, NULL, 1, 1),
(82, 'A2', 2, 1, 1, 1, NULL, 1, 1),
(83, 'A3', 2, 1, 1, 1, NULL, 1, 1),
(84, 'B1', 2, 1, 1, 2, NULL, 1, 1),
(85, 'B2', 2, 1, 1, 2, NULL, 1, 1),
(86, 'B3', 2, 1, 1, 2, NULL, 1, 1);

-- items_group: 2 rows
INSERT INTO `items_group` (`id`, `group_name`, `items_id`, `unit_id`) VALUES
(1, 'សៀវភៅមតេ្តយ្យសិក្សាកម្រិតខ្ពស់', '45,46', -1),
(2, 'សៀវភៅមតេ្តយ្យសិក្សាកម្រិតមធ្បម', '47,48', -1);

-- learning_time_slots: 48 rows
INSERT INTO `learning_time_slots` (`id`, `slot_name`, `start_time`, `end_time`, `duration_minutes`, `sort_order`, `is_active`, `is_global`, `grade_group_id`, `grade_id`) VALUES
(1, 'M-Session 1', '7:30:00', '8:10:00', NULL, 1, 1, 1, NULL, NULL),
(2, 'M-Session 2', '8:10:00', '8:50:00', NULL, 2, 1, 1, NULL, NULL),
(3, 'M-Session 3', '9:10:00', '9:50:00', NULL, 3, 1, 1, NULL, NULL),
(4, 'M-Session 4', '9:50:00', '10:30:00', NULL, 4, 1, 1, NULL, NULL),
(5, 'M-Session 5', '10:30:00', '11:00:00', NULL, 5, 1, 1, NULL, NULL),
(6, 'M-Session 6', '11:00:00', '12:00:00', NULL, 6, 1, 1, NULL, NULL),
(7, 'PM-Session 1', '12:00:00', '13:00:00', NULL, 7, 1, 1, NULL, NULL),
(8, 'PM-Session 2', '13:00:00', '14:40:00', NULL, 8, 1, 1, NULL, NULL),
(9, 'PM-Session 3', '13:40:00', '14:20:00', NULL, 9, 1, 1, NULL, NULL),
(10, 'PM-Session 4', '14:40:00', '15:20:00', NULL, 10, 1, 1, NULL, NULL),
(11, 'PM-Session 5', '15:20:00', '16:00:00', NULL, 11, 1, 1, NULL, NULL),
(12, 'PM-Session 6', '16:00:00', '16:40:00', NULL, 12, 1, 1, NULL, NULL),
(13, 'MK-Session 1', '7:30:00', '8:00:00', NULL, 13, 1, 1, NULL, NULL),
(14, 'MK-Session 2', '8:00:00', '8:30:00', NULL, 14, 1, 1, NULL, NULL),
(15, 'MK-Session 3', '8:45:00', '9:15:00', NULL, 15, 1, 1, NULL, NULL),
(16, 'MK-Session 4', '9:15:00', '9:45:00', NULL, 16, 1, 1, NULL, NULL),
(17, 'MK-Session 5', '10:00:00', '10:45:00', NULL, 17, 1, 1, NULL, NULL),
(18, 'PK-Session 1', '13:00:00', '13:30:00', NULL, 18, 1, 1, NULL, NULL),
(19, 'PK-Session 2', '13:30:00', '14:00:00', NULL, 19, 1, 1, NULL, NULL),
(20, 'PK-Session 3', '14:15:00', '14:45:00', NULL, 20, 1, 1, NULL, NULL),
(21, 'PK-Session 4', '14:45:00', '15:15:00', NULL, 21, 1, 1, NULL, NULL),
(22, 'PK-Session 5', '15:30:00', '16:15:00', NULL, 22, 1, 1, NULL, NULL),
(23, 'MI-Session 1', '7:30:00', '8:30:00', NULL, 23, 1, 1, NULL, NULL),
(24, 'MI-Session 2', '8:45:00', '9:25:00', NULL, 24, 1, 1, NULL, NULL),
(25, 'MI-Session 3', '9:40:00', '10:20:00', NULL, 25, 1, 1, NULL, NULL),
(26, 'MI-Session 4', '10:20:00', '11:00:00', NULL, 26, 1, 1, NULL, NULL),
(27, 'PI-Session 1', '13:00:00', '14:00:00', NULL, 27, 1, 1, NULL, NULL),
(28, 'PI-Session 2', '14:15:00', '14:55:00', NULL, 28, 1, 1, NULL, NULL),
(29, 'PI-Session 3', '15:10:00', '15:50:00', NULL, 29, 1, 1, NULL, NULL),
(30, 'PI-Session 4', '15:50:00', '16:30:00', NULL, 30, 1, 1, NULL, NULL),
(31, 'MW-Session 1', '7:30:00', '8:15:00', NULL, 31, 1, 1, NULL, NULL),
(32, 'MW-Session 2', '8:15:00', '9:00:00', NULL, 32, 1, 1, NULL, NULL),
(33, 'MW-Session 3', '9:30:00', '10:15:00', NULL, 33, 1, 1, NULL, NULL),
(34, 'MW-Session 4', '10:15:00', '11:00:00', NULL, 34, 1, 1, NULL, NULL),
(35, 'PW-Session 1', '13:00:00', '13:45:00', NULL, 35, 1, 1, NULL, NULL),
(36, 'PW-Session 2', '13:45:00', '14:30:00', NULL, 36, 1, 1, NULL, NULL),
(37, 'PW-Session 3', '15:00:00', '15:45:00', NULL, 37, 1, 1, NULL, NULL),
(38, 'PW-Session 4', '15:45:00', '16:45:00', NULL, 38, 1, 1, NULL, NULL),
(39, 'PH-Session 1', '12:00:00', '12:50:00', NULL, 39, 1, 1, NULL, NULL),
(40, 'PH-Session 2', '13:00:00', '13:50:00', NULL, 40, 1, 1, NULL, NULL),
(41, 'PH-Session 3', '14:00:00', '14:50:00', NULL, 41, 1, 1, NULL, NULL),
(42, 'PH-Session 4', '15:00:00', '15:50:00', NULL, 42, 1, 1, NULL, NULL),
(43, 'PH-Session 5', '16:00:00', '16:50:00', NULL, 43, 1, 1, NULL, NULL),
(44, 'PH-Session 6', '17:00:00', '17:50:00', NULL, 44, 1, 1, NULL, NULL),
(45, 'MH-Session 1', '8:00:00', '8:50:00', NULL, 45, 1, 1, NULL, NULL),
(46, 'MH-Session 2', '9:00:00', '9:50:00', NULL, 46, 1, 1, NULL, NULL),
(47, 'MH-Session 3', '10:00:00', '10:50:00', NULL, 47, 1, 1, NULL, NULL),
(48, 'MH-Session 4', '11:00:00', '11:50:00', NULL, 48, 1, 1, NULL, NULL);

-- leave_types: 5 rows
INSERT INTO `leave_types` (`id`, `name`, `description`, `max_days_per_year`, `is_paid`, `requires_approval`, `requires_proof`, `is_active`, `display_order`, `color_hex`, `max_days_per_month`) VALUES
(1, 'Annual Leave', '', 0.0e0, 1, 1, 0, 1, 1, '#7C3AED', 1.0e0),
(2, 'Sick Leave', '', 0.0e0, 1, 1, 1, 1, 2, '#42A5F5', NULL),
(4, 'Marriage Leave', '', 0.0e0, 1, 1, 1, 1, 4, '#FFB300', NULL),
(5, 'Dead leave or Funeral', '', 0.0e0, 1, 1, 0, 1, 5, '#E91E63', NULL),
(9, 'Other leave', NULL, 10.0e0, 0, 1, 0, 1, 5, '#FFB300', NULL);

-- market_categories: 5 rows
INSERT INTO `market_categories` (`id`, `name`, `name_en`, `name_km`, `icon_key`, `sort_order`) VALUES
(1, 'Books', 'Books', 'សៀវភៅ', 'books', 1),
(2, 'Uniform', 'Uniform', 'ឯកសណ្ឋាន', 'uniform', 2),
(3, 'Food', 'Food', 'អាហារ', 'food', 3),
(4, 'Electronics', 'Electronics', 'អេឡិចត្រូនិច', 'electronics', 4),
(5, 'Other', 'Other', 'ផ្សេងៗ', 'other', 99);

-- market_settings: 1 rows
INSERT INTO `market_settings` (`id`, `welcome_enabled`, `welcome_skip_seconds`, `welcome_version`) VALUES
(1, 0, 30, 1);

-- marks_system: 52 rows
INSERT INTO `marks_system` (`id`, `marks_name`, `marks_code`, `subjects_ids`, `grade_group_id`, `program_id`, `for_month`, `academic_id`, `created_by`, `updated_by`, `status`) VALUES
(83, 'ខែកញ្ញា', 'MON1', NULL, 29, 1, '2026-09-17', 1, 1, 1, 1),
(84, 'ខែតុលា', 'MON2', NULL, 29, 1, '2026-10-22', 1, 1, 1, 1),
(85, 'ខែធ្នូ', 'MON4', NULL, 29, 1, '2026-12-15', 1, 1, 1, 1),
(86, 'ខែកុម្ភៈ', 'MON5', NULL, 29, 1, '2027-02-23', 1, 1, 1, 1),
(87, 'ខែមីនា', 'MON6', NULL, 29, 1, '2027-03-23', 1, 1, 1, 1),
(88, 'ខែមេសា', 'MON7', NULL, 29, 1, '2027-04-22', 1, 1, 1, 1),
(89, 'ខែវិច្ឆិកា', 'MON3', NULL, 29, 1, '2026-12-31', 1, 1, 1, 1),
(90, 'ឆមាសទី១', 'SEM1', NULL, 29, 1, '2027-01-11', 1, 1, 1, 1),
(91, 'ឆមាសទី២', 'SEM2', NULL, 29, 1, '2027-06-08', 1, 1, 1, 1),
(92, 'ខែឧសភា', 'MON8', NULL, 29, 1, '2027-05-20', 1, 1, 1, 1),
(93, 'ខែកញ្ញា', 'MON1', NULL, 28, 1, '2027-01-04', 1, 1, 1, 1),
(94, 'ខែតុលា', 'MON2', NULL, 28, 1, '2027-01-04', 1, 1, 1, 1),
(95, 'ខែវិច្ឆិកា', 'MON3', NULL, 28, 1, '2027-01-04', 1, 1, 1, 1),
(96, 'ខែធ្នូ', 'MON4', NULL, 28, 1, '2026-12-15', 1, 1, 1, 1),
(97, 'ឆមាសទី១', 'SEM1', NULL, 28, 1, '2027-01-11', 1, 1, 1, 1),
(98, 'ខែមីនា', 'MON6', NULL, 28, 1, '2027-03-23', 1, 1, 1, 1),
(99, 'ខែមេសា', 'MON7', NULL, 28, 1, '2027-04-22', 1, 1, 1, 1),
(100, 'ខែឧសភា', 'MON8', NULL, 28, 1, '2027-05-20', 1, 1, 1, 1),
(101, 'ខែកុម្ភៈ', 'MON5', NULL, 28, 1, '2027-02-23', 1, 1, 1, 1),
(102, 'ឆមាសទី២', 'SEM2', NULL, 28, 1, '2027-06-08', 1, 1, 1, 1),
(113, 'Mid- 1st Quarter', 'MON1', NULL, 33, 3, '2026-09-28', 1, 1, 1, 1),
(114, 'Final- 1st Quarter', 'MON2', NULL, 33, 3, '2026-10-27', 1, 1, 1, 1),
(115, 'Mid- 2nd Quarter', 'MON3', NULL, 33, 3, '2026-12-15', 1, 1, 1, 1),
(116, 'Final- 2nd Quarter', 'MON4', NULL, 33, 3, '2027-01-19', 1, 1, 1, 1),
(117, 'Mid- 3rd Quarter', 'MON5', NULL, 33, 3, '2027-03-10', 1, 1, 1, 1),
(118, 'Final- 3rd Quarter', 'MON6', NULL, 33, 3, '2027-04-06', 1, 1, 1, 1),
(119, 'Mid- 4th Quarter', 'MON7', NULL, 33, 3, '2027-05-25', 1, 1, 1, 1),
(120, 'Final- 4th Quarter', 'MON8', NULL, 33, 3, '2027-06-21', 1, 1, 1, 1),
(121, 'Mid- 1st Quarter', 'MON1', NULL, 36, 2, '2026-11-02', 1, 1, 1, 1),
(122, 'Final- 1st Quarter', 'MON2', NULL, 36, 2, '2026-10-27', 1, 1, 1, 1),
(123, 'Mid- 2nd Quarter', 'MON3', NULL, 36, 2, '2026-12-15', 1, 1, 1, 1),
(124, 'Final- 2nd Quarter', 'MON4', NULL, 36, 2, '2027-01-19', 1, 1, 1, 1),
(125, 'Mid- 3rd Quarter', 'MON5', NULL, 36, 2, '2027-03-10', 1, 1, 1, 1),
(126, 'Final- 3rd Quarter', 'MON6', NULL, 36, 2, '2027-04-06', 1, 1, 1, 1),
(127, 'Mid- 4th Quarter', 'MON7', NULL, 36, 2, '2027-05-25', 1, 1, 1, 1),
(128, 'Final- 4th Quarter', 'MON8', NULL, 36, 2, '2027-06-21', 1, 1, 1, 1),
(129, 'Mid- 1st Quarter', 'MON1', NULL, 34, 2, '2026-09-28', 1, 1, 1, 1),
(130, 'Final- 1st Quarter', 'MON2', NULL, 34, 2, '2026-10-27', 1, 1, 1, 1),
(131, 'Mid- 2nd Quarter', 'MON3', NULL, 34, 2, '2026-12-15', 1, 1, 1, 1),
(132, 'Final- 2nd Quarter', 'MON4', NULL, 34, 2, '2027-01-19', 1, 1, 1, 1),
(133, 'Mid- 3rd Quarter', 'MON5', NULL, 34, 2, '2027-03-10', 1, 1, 1, 1),
(134, 'Final- 3rd Quarter', 'MON6', NULL, 34, 2, '2027-04-06', 1, 1, 1, 1),
(135, 'Mid- 4th Quarter', 'MON7', NULL, 34, 2, '2027-05-25', 1, 1, 1, 1),
(136, 'Final- 4th Quarter', 'MON8', NULL, 34, 2, '2027-06-21', 1, 1, 1, 1),
(137, 'Mid- 1st Quarter', 'MON1', NULL, 35, 2, '2026-09-28', 1, 1, 1, 1),
(138, 'Final- 1st Quarter', 'MON2', NULL, 35, 2, '2026-10-27', 1, 1, 1, 1),
(139, 'Mid- 2nd Quarter', 'MON3', NULL, 35, 2, '2026-12-15', 1, 1, 1, 1),
(140, 'Final- 2nd Quarter', 'MON4', NULL, 35, 2, '2027-01-19', 1, 1, 1, 1),
(141, 'Mid- 3rd Quarter', 'MON5', NULL, 35, 2, '2027-03-10', 1, 1, 1, 1),
(142, 'Final- 3rd Quarter', 'MON6', NULL, 35, 2, '2027-04-06', 1, 1, 1, 1),
(143, 'Mid- 4th Quarter', 'MON7', NULL, 35, 2, '2027-05-25', 1, 1, 1, 1),
(144, 'Final- 4th Quarter', 'MON8', NULL, 35, 2, '2027-06-21', 1, 1, 1, 1);

-- marks_system_subjects: 394 rows
INSERT INTO `marks_system_subjects` (`id`, `marks_system_id`, `subject_id`) VALUES
(3122, 83, 1),
(3123, 83, 2),
(3124, 83, 3),
(3125, 83, 4),
(3126, 83, 5),
(3127, 83, 6),
(3128, 83, 7),
(3129, 83, 8),
(3130, 83, 9),
(3131, 83, 10),
(3132, 83, 11),
(3133, 84, 1),
(3134, 84, 2),
(3135, 84, 3),
(3136, 84, 4),
(3137, 84, 5),
(3138, 84, 6),
(3139, 84, 7),
(3140, 84, 8),
(3141, 84, 9),
(3142, 84, 10),
(3143, 84, 11),
(3144, 85, 1),
(3145, 85, 2),
(3146, 85, 3),
(3147, 85, 4),
(3148, 85, 5),
(3149, 85, 6),
(3150, 85, 7),
(3151, 85, 8),
(3152, 85, 9),
(3153, 85, 10),
(3154, 85, 11),
(3155, 86, 1),
(3156, 86, 2),
(3157, 86, 3),
(3158, 86, 4),
(3159, 86, 5),
(3160, 86, 6),
(3161, 86, 7),
(3162, 86, 8),
(3163, 86, 9),
(3164, 86, 10),
(3165, 86, 11),
(3166, 87, 1),
(3167, 87, 2),
(3168, 87, 3),
(3169, 87, 4),
(3170, 87, 5),
(3171, 87, 6),
(3172, 87, 7),
(3173, 87, 8),
(3174, 87, 9),
(3175, 87, 10),
(3176, 87, 11),
(3177, 88, 1),
(3178, 88, 2),
(3179, 88, 3),
(3180, 88, 4),
(3181, 88, 5),
(3182, 88, 6),
(3183, 88, 7),
(3184, 88, 8),
(3185, 88, 9),
(3186, 88, 10),
(3187, 88, 11),
(3188, 89, 1),
(3189, 89, 2),
(3190, 89, 3),
(3191, 89, 4),
(3192, 89, 5),
(3193, 89, 6),
(3194, 89, 7),
(3195, 89, 8),
(3196, 89, 9),
(3197, 89, 10),
(3198, 89, 11),
(3199, 90, 1),
(3200, 90, 2),
(3201, 90, 3),
(3202, 90, 4),
(3203, 90, 5),
(3204, 90, 6),
(3205, 90, 7),
(3206, 90, 8),
(3207, 90, 9),
(3208, 90, 10),
(3209, 90, 11),
(3210, 91, 1),
(3211, 91, 2),
(3212, 91, 3),
(3213, 91, 4),
(3214, 91, 5),
(3215, 91, 6),
(3216, 91, 7),
(3217, 91, 8),
(3218, 91, 9),
(3219, 91, 10),
(3220, 91, 11),
(3221, 92, 1);
INSERT INTO `marks_system_subjects` (`id`, `marks_system_id`, `subject_id`) VALUES
(3222, 92, 2),
(3223, 92, 3),
(3224, 92, 4),
(3225, 92, 5),
(3226, 92, 6),
(3227, 92, 7),
(3228, 92, 8),
(3229, 92, 9),
(3230, 92, 10),
(3231, 92, 11),
(3232, 93, 25),
(3233, 93, 26),
(3234, 93, 27),
(3235, 93, 28),
(3236, 93, 29),
(3237, 93, 30),
(3238, 94, 25),
(3239, 94, 26),
(3240, 94, 27),
(3241, 94, 28),
(3242, 94, 29),
(3243, 94, 30),
(3244, 95, 25),
(3245, 95, 26),
(3246, 95, 27),
(3247, 95, 28),
(3248, 95, 29),
(3249, 95, 30),
(3250, 96, 25),
(3251, 96, 26),
(3252, 96, 27),
(3253, 96, 28),
(3254, 96, 29),
(3255, 96, 30),
(3256, 97, 25),
(3257, 97, 26),
(3258, 97, 27),
(3259, 97, 28),
(3260, 97, 29),
(3261, 97, 30),
(3262, 98, 25),
(3263, 98, 26),
(3264, 98, 27),
(3265, 98, 28),
(3266, 98, 29),
(3267, 98, 30),
(3268, 99, 25),
(3269, 99, 26),
(3270, 99, 27),
(3271, 99, 28),
(3272, 99, 29),
(3273, 99, 30),
(3274, 100, 25),
(3275, 100, 26),
(3276, 100, 27),
(3277, 100, 28),
(3278, 100, 29),
(3279, 100, 30),
(3280, 101, 25),
(3281, 101, 26),
(3282, 101, 27),
(3283, 101, 28),
(3284, 101, 29),
(3285, 101, 30),
(3286, 102, 25),
(3287, 102, 26),
(3288, 102, 27),
(3289, 102, 28),
(3290, 102, 29),
(3291, 102, 30),
(3442, 113, 31),
(3443, 113, 32),
(3444, 113, 33),
(3445, 113, 34),
(3446, 113, 35),
(3447, 113, 36),
(3448, 113, 37),
(3449, 114, 31),
(3450, 114, 32),
(3451, 114, 33),
(3452, 114, 34),
(3453, 114, 35),
(3454, 114, 36),
(3455, 114, 37),
(3456, 115, 31),
(3457, 115, 32),
(3458, 115, 33),
(3459, 115, 34),
(3460, 115, 35),
(3461, 115, 36),
(3462, 115, 37),
(3463, 116, 31),
(3464, 116, 32),
(3465, 116, 33),
(3466, 116, 34),
(3467, 116, 35),
(3468, 116, 36),
(3469, 116, 37),
(3470, 117, 31),
(3471, 117, 32);
INSERT INTO `marks_system_subjects` (`id`, `marks_system_id`, `subject_id`) VALUES
(3472, 117, 33),
(3473, 117, 34),
(3474, 117, 35),
(3475, 117, 36),
(3476, 117, 37),
(3477, 118, 31),
(3478, 118, 32),
(3479, 118, 33),
(3480, 118, 34),
(3481, 118, 35),
(3482, 118, 36),
(3483, 118, 37),
(3484, 119, 31),
(3485, 119, 32),
(3486, 119, 33),
(3487, 119, 34),
(3488, 119, 35),
(3489, 119, 36),
(3490, 119, 37),
(3491, 120, 31),
(3492, 120, 32),
(3493, 120, 33),
(3494, 120, 34),
(3495, 120, 35),
(3496, 120, 36),
(3497, 120, 37),
(3498, 121, 38),
(3499, 121, 39),
(3500, 121, 40),
(3501, 121, 41),
(3502, 121, 42),
(3503, 121, 43),
(3504, 121, 44),
(3505, 122, 38),
(3506, 122, 39),
(3507, 122, 40),
(3508, 122, 41),
(3509, 122, 42),
(3510, 122, 43),
(3511, 122, 44),
(3512, 123, 38),
(3513, 123, 39),
(3514, 123, 40),
(3515, 123, 41),
(3516, 123, 42),
(3517, 123, 43),
(3518, 123, 44),
(3519, 124, 38),
(3520, 124, 39),
(3521, 124, 40),
(3522, 124, 41),
(3523, 124, 42),
(3524, 124, 43),
(3525, 124, 44),
(3526, 125, 38),
(3527, 125, 39),
(3528, 125, 40),
(3529, 125, 41),
(3530, 125, 42),
(3531, 125, 43),
(3532, 125, 44),
(3533, 126, 38),
(3534, 126, 39),
(3535, 126, 40),
(3536, 126, 41),
(3537, 126, 42),
(3538, 126, 43),
(3539, 126, 44),
(3540, 127, 38),
(3541, 127, 39),
(3542, 127, 40),
(3543, 127, 41),
(3544, 127, 42),
(3545, 127, 43),
(3546, 127, 44),
(3547, 128, 38),
(3548, 128, 39),
(3549, 128, 40),
(3550, 128, 41),
(3551, 128, 42),
(3552, 128, 43),
(3553, 128, 44),
(3554, 129, 38),
(3555, 129, 39),
(3556, 129, 40),
(3557, 129, 41),
(3558, 129, 42),
(3559, 129, 43),
(3560, 129, 44),
(3561, 130, 38),
(3562, 130, 39),
(3563, 130, 40),
(3564, 130, 41),
(3565, 130, 42),
(3566, 130, 43),
(3567, 130, 44),
(3568, 131, 38),
(3569, 131, 39),
(3570, 131, 40),
(3571, 131, 41);
INSERT INTO `marks_system_subjects` (`id`, `marks_system_id`, `subject_id`) VALUES
(3572, 131, 42),
(3573, 131, 43),
(3574, 131, 44),
(3575, 132, 38),
(3576, 132, 39),
(3577, 132, 40),
(3578, 132, 41),
(3579, 132, 42),
(3580, 132, 43),
(3581, 132, 44),
(3582, 133, 38),
(3583, 133, 39),
(3584, 133, 40),
(3585, 133, 41),
(3586, 133, 42),
(3587, 133, 43),
(3588, 133, 44),
(3589, 134, 38),
(3590, 134, 39),
(3591, 134, 40),
(3592, 134, 41),
(3593, 134, 42),
(3594, 134, 43),
(3595, 134, 44),
(3596, 135, 38),
(3597, 135, 39),
(3598, 135, 40),
(3599, 135, 41),
(3600, 135, 42),
(3601, 135, 43),
(3602, 135, 44),
(3603, 136, 38),
(3604, 136, 39),
(3605, 136, 40),
(3606, 136, 41),
(3607, 136, 42),
(3608, 136, 43),
(3609, 136, 44),
(3610, 137, 38),
(3611, 137, 39),
(3612, 137, 40),
(3613, 137, 41),
(3614, 137, 42),
(3615, 137, 43),
(3616, 137, 44),
(3617, 138, 38),
(3618, 138, 39),
(3619, 138, 40),
(3620, 138, 41),
(3621, 138, 42),
(3622, 138, 43),
(3623, 138, 44),
(3624, 139, 38),
(3625, 139, 39),
(3626, 139, 40),
(3627, 139, 41),
(3628, 139, 42),
(3629, 139, 43),
(3630, 139, 44),
(3631, 140, 38),
(3632, 140, 39),
(3633, 140, 40),
(3634, 140, 41),
(3635, 140, 42),
(3636, 140, 43),
(3637, 140, 44),
(3638, 141, 38),
(3639, 141, 39),
(3640, 141, 40),
(3641, 141, 41),
(3642, 141, 42),
(3643, 141, 43),
(3644, 141, 44),
(3645, 142, 38),
(3646, 142, 39),
(3647, 142, 40),
(3648, 142, 41),
(3649, 142, 42),
(3650, 142, 43),
(3651, 142, 44),
(3652, 143, 38),
(3653, 143, 39),
(3654, 143, 40),
(3655, 143, 41),
(3656, 143, 42),
(3657, 143, 43),
(3658, 143, 44),
(3659, 144, 38),
(3660, 144, 39),
(3661, 144, 40),
(3662, 144, 41),
(3663, 144, 42),
(3664, 144, 43),
(3665, 144, 44);

-- medal_points_setup: 96 rows
INSERT INTO `medal_points_setup` (`program_name`, `gold_pts`, `silver_pts`, `bronze_pts`, `diamond_pts`, `participation_pts`) VALUES
('AMC FINAL', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('AMO', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 0.5e0),
('BBB', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 1.0e0),
('BEBRAS', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 0.0e0),
('BMC', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('CIMOC FINAL', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('CIMOC PRE', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('COPERNICUS MATH', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('Dream', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('ESB FINAL', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('ESB PRELIMINARY', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('FISO GR ENG', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('FISO GR MATH', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('FISO GR SCI', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('FISO IR ARTS', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('FISO IR ENG', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('FISO IR IQ', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('FISO IR MATH', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('FISO IR SCI', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('FISO NR ART', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('FISO NR ENG', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('FISO NR IQ', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('FISO NR MATH', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('FISO NR SCI', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('FISO NR TECH', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('GMC', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('HKIMO', 0.0e0, 0.0e0, 0.0e0, 0.0e0, 0.0e0),
('HKIMO IR', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('HKIMO NR', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('IEMO NR ENG', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('IESO IR', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('IESO NR SCI', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('IMOCSEA NR MATH', 4.0e0, 3.0e0, 2.0e0, 5.0e0, 1.0e0),
('ISOCSEA NR SCI', 4.0e0, 3.0e0, 2.0e0, 5.0e0, 1.0e0),
('KOALA/ARTS', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('KOALA/ENGLISH', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('KOALA/MATH', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('KOALA/SCIENCE', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('Linker Scientia Cup', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Linker/Bio', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Linker/Chemistry', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Linker/Math', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Linker/Physic', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Math Kangaroo', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.5e0),
('MPCH', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Outstanding students', 3.0e0, 2.0e0, 1.0e0, 0.0e0, 0.0e0),
('PHIMO IR', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('PHIMO NR MATH', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('Picture Prompts', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('PIMSO IR MATH', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('PIMSO IR SCI', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('PIMSO NR MATH', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('PIMSO NR SCI', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('Public Speaking', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Reading Contest', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Romdul Scholars Challenge', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Romdul/Art', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Romdul/Geo', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Romdul/History', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Romdul/Math', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Romdul/science', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('SASMO', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('SEAMO', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 0.5e0),
('SEAMOX IR', 7.0e0, 6.0e0, 5.0e0, 0.0e0, 3.0e0),
('Show and Tell', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('SIMSO/MATH', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('SIMSO/SCIENCE', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('SMC', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('SMGF', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('Spelling Bee', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('Story Telling', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('TEENEAGLE', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('TIMO', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 1.0e0),
('TIMO IR', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('VIAMC', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 0.5e0),
('VIAMC IR', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('WEC', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('WMC', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('WMI', 4.0e0, 3.0e0, 2.0e0, 0.0e0, 0.5e0),
('WSC IR SCI', 5.0e0, 4.0e0, 3.0e0, 0.0e0, 2.0e0),
('WSC/Debate', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('WSC/Scholar\'s Bowl', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('WSC/Scholar\'s Challenge', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('WSC/TEAM DEBATE', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('WSC/TEAM WRITING', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('WSC/Writing', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('កម្មវិធីប៉ាម៉ា', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('តែងសេក្ដី', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('និយាយជាសាធារណៈ', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('បទបង្ហាញអមដោយរូបភាព', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('ប្រកបពាក្យ និងអក្ខរវិញ្ញាស', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('ប្រកួតនិទានរឿង', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('ប្រកួតអំណាន និងស្មូត្រកំណាព្យ', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('សំណេរ និងអត្ថន័យពាក្យ', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('សិស្សឆ្នើម', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0),
('អំណាន និងកំណាព្យ', 2.0e0, 1.0e0, 0.5e0, 0.0e0, 0.0e0);

-- medalname: 93 rows
INSERT INTO `medalname` (`id`, `medal_name`) VALUES
(1, 'កម្មវិធីប៉ាម៉ា'),
(2, 'ប្រកបពាក្យ និងអក្ខរវិញ្ញាស'),
(3, 'អំណាន និងកំណាព្យ'),
(4, 'ប្រកួតនិទានរឿង'),
(5, 'បទបង្ហាញអមដោយរូបភាព'),
(6, 'និយាយជាសាធារណៈ'),
(7, 'តែងសេក្ដី'),
(8, 'សិស្សឆ្នើម'),
(9, 'Picture Prompts'),
(10, 'Outstanding students'),
(11, 'Story Telling'),
(12, 'Show and Tell'),
(13, 'Public Speaking'),
(14, 'Reading Contest'),
(17, 'ISOCSEA NR SCI'),
(18, 'សំណេរ និងអត្ថន័យពាក្យ'),
(19, 'ប្រកួតអំណាន និងស្មូត្រកំណាព្យ'),
(20, 'IMOCSEA NR MATH'),
(21, 'SMC'),
(23, 'SEAMO'),
(24, 'AMO'),
(25, 'TEENEAGLE'),
(26, 'TIMO'),
(27, 'AMC FINAL'),
(28, 'IGC'),
(35, 'PIMSO NR MATH'),
(36, 'PIMSO NR SCI'),
(37, 'WMI'),
(38, 'SASMO'),
(39, 'BBB'),
(42, 'IMEC'),
(43, 'MPCH'),
(44, 'BMC'),
(46, 'Dream'),
(48, 'CIMOC PRE'),
(51, 'VIAMC'),
(52, 'SEAMOX IR'),
(53, 'BEBRAS'),
(54, 'SIMSO/MATH'),
(55, 'SIMSO/SCIENCE'),
(57, 'WMC'),
(58, 'WEC'),
(59, 'Math Kangaroo'),
(60, 'Romdul Scholars Challenge'),
(61, 'WSC/Scholar\'s Bowl'),
(62, 'WSC/Writing'),
(63, 'WSC/Debate'),
(64, 'WSC/Scholar\'s Challenge'),
(65, 'WSC/TEAM WRITING'),
(66, 'WSC/TEAM DEBATE'),
(67, 'KOALA/ENGLISH'),
(68, 'KOALA/MATH'),
(69, 'KOALA/SCIENCE'),
(70, 'KOALA/ARTS'),
(71, 'IESO NR SCI'),
(73, 'Linker Scientia Cup'),
(74, 'Linker/Math'),
(75, 'Linker/Bio'),
(76, 'Linker/Chemistry'),
(77, 'Linker/Physic'),
(78, 'Romdul/Math'),
(79, 'Romdul/science'),
(80, 'Romdul/Geo'),
(81, 'Romdul/History'),
(82, 'Romdul/Art'),
(83, 'CIMOC FINAL'),
(85, 'PHIMO NR MATH'),
(86, 'COPERNICUS MATH'),
(90, 'GMC'),
(91, 'IESO IR'),
(92, 'PHIMO IR'),
(93, 'SMGF'),
(94, 'WSC IR SCI'),
(95, 'ESB PRELIMINARY'),
(96, 'ESB FINAL'),
(97, 'FISO IR ARTS'),
(98, 'FISO IR ENG'),
(99, 'FISO IR IQ'),
(100, 'FISO IR MATH'),
(101, 'FISO IR SCI'),
(102, 'FISO NR ART'),
(103, 'FISO NR ENG'),
(104, 'FISO NR IQ'),
(105, 'FISO NR MATH'),
(106, 'FISO NR SCI'),
(107, 'FISO NR TECH'),
(108, 'HKIMO IR'),
(109, 'HKIMO NR'),
(110, 'IEMO NR ENG'),
(111, 'PIMSO IR MATH'),
(112, 'PIMSO IR SCI'),
(113, 'TIMO IR'),
(114, 'VIAMC IR');

-- nittes: 6 rows
INSERT INTO `nittes` (`id`, `name_us`, `name_kh`) VALUES
(1, 'A', 'ល្អប្រសើរ'),
(2, 'B', 'ល្អណាស់'),
(3, 'C', 'ល្អ'),
(4, 'D', 'បង្គួរ'),
(5, 'E', 'មធ្យម'),
(6, 'F', 'ក្រោមមធ្យម');

-- permissions: 109 rows
INSERT INTO `permissions` (`id`, `permission_name`, `description`) VALUES
(1, 'ViewStudent', 'View student information'),
(2, 'AddStudent', 'Add new students'),
(3, 'UpdateStudent', 'Edit student details'),
(4, 'DeleteStudent', 'Delete student records'),
(5, 'ViewTeacher', 'View teacher information'),
(6, 'AddTeacher', 'Add new teachers'),
(7, 'UpdateTeacher', 'Edit teacher details'),
(8, 'DeleteTeacher', 'Remove teacher records'),
(9, 'ViewClass', 'View classes or courses'),
(10, 'AddClass', 'Add new classes or courses'),
(11, 'UpdateClass', 'Edit class/course details'),
(12, 'DeleteClass', 'Delete classes'),
(13, 'ViewAttendance', 'View attendance records'),
(14, 'AddAttendance', 'Add attendance records'),
(15, 'UpdateAttendance', 'Edit attendance'),
(16, 'DeleteAttendance', 'Delete attendance records'),
(17, 'ViewGrades', 'View student grades'),
(18, 'AddGrades', 'Enter grades'),
(19, 'UpdateGrades', 'Edit grades'),
(20, 'DeleteGrades', 'Remove grades'),
(21, 'ViewReports', 'View various reports'),
(22, 'GenerateReports', 'Generate or export reports'),
(23, 'ManageUsers', 'Manage user accounts and roles'),
(24, 'ManageRoles', 'Create/edit/delete roles and permissions'),
(25, 'ViewAllBranches', 'View all Branch'),
(26, 'ViewAdminDashboard', NULL),
(27, 'ViewTeacherDashboard', ''),
(28, 'DeleteReceipt', 'Delete invoice'),
(29, 'ViewAccounts', NULL),
(30, 'ViewReceipt', NULL),
(31, 'ChangeRole', NULL),
(32, 'UserPassword', NULL),
(34, 'ClearAccounts', NULL),
(35, 'UpdateSettings', NULL),
(36, 'DashboardBasic', NULL),
(37, 'DashboardAccounting', NULL),
(38, 'GeneralDelete', NULL),
(39, 'GeneralUpdate', NULL),
(40, 'GeneralAdd', NULL),
(41, 'AdminViewApp', 'View App settings'),
(42, 'AdminUpdateApp', 'Update App settings'),
(43, 'AdminDeleteApp', 'Delete App settings'),
(44, 'ViewInvoices', NULL),
(45, 'ViewUpcomingInvoices', NULL),
(46, 'ViewInventories', NULL),
(47, 'ViewPricing', NULL),
(48, 'ViewFeeServices', NULL),
(49, 'AddAccount', NULL),
(50, 'EditAccount', NULL),
(51, 'EditInvoice', NULL),
(52, 'AddInventory', NULL),
(53, 'EditInventory', NULL),
(54, 'DeleteInventory', NULL),
(55, 'AddPricing', NULL),
(56, 'EditPricing', NULL),
(57, 'DeletePricing', NULL),
(58, 'AddFeeService', NULL),
(59, 'EditFeeService', NULL),
(60, 'DeleteFeeService', NULL),
(61, 'AddDiscount', NULL),
(62, 'EditDiscount', NULL),
(63, 'DeleteDiscount', NULL),
(64, 'ViewDashboard', NULL),
(65, 'ViewStudents', NULL),
(66, 'ViewStudentsByClass', NULL),
(67, 'ViewStudentTeachers', NULL),
(68, 'ViewStudentPrograms', NULL),
(69, 'ViewScholarship', NULL),
(70, 'ViewCertificate', NULL),
(71, 'ViewMedals', NULL),
(72, 'ViewAchievement', NULL),
(73, 'ViewStoppedStudents', NULL),
(74, 'ViewParents', NULL),
(75, 'ViewParentPayments', NULL),
(76, 'ViewParentPickupReport', NULL),
(77, 'ViewEmployees', NULL),
(78, 'ViewPendingEmployees', NULL),
(79, 'ViewStoppedEmployees', NULL),
(80, 'ViewDepartments', NULL),
(81, 'ViewClassTeacherAssignment', NULL),
(82, 'ViewCalendar', NULL),
(83, 'ViewAcademic', NULL),
(84, 'ViewBranch', NULL),
(85, 'ViewGradeTypes', NULL),
(86, 'ViewGradeGroups', NULL),
(87, 'ViewPrograms', NULL),
(88, 'ViewShifts', NULL),
(89, 'ViewExamSystem', NULL),
(90, 'ViewMarksSystem', NULL),
(91, 'ViewMarkSubjects', NULL),
(92, 'ViewSubjects', NULL),
(93, 'ViewSubjectGroups', NULL),
(94, 'ViewNites', NULL),
(95, 'ViewExpense', NULL),
(96, 'ViewExpenseCategories', NULL),
(97, 'AddExpense', NULL),
(98, 'EditExpense', NULL),
(99, 'DeleteExpense', NULL),
(100, 'AddExpenseCategory', NULL),
(101, 'EditExpenseCategory', NULL);
INSERT INTO `permissions` (`id`, `permission_name`, `description`) VALUES
(102, 'DeleteExpenseCategory', NULL),
(103, 'ViewBuses', NULL),
(104, 'ViewBusAttendance', NULL),
(105, 'ViewBusStops', NULL),
(106, 'ViewBusStopPrices', NULL),
(107, 'ViewBusDriverAssignment', NULL),
(108, 'ViewBusStudentEnrollment', NULL),
(109, 'ViewActivityLogs', NULL),
(110, 'ReviewStudentProfileEdits', NULL);

-- pickup_branch_calling: 1 rows
INSERT INTO `pickup_branch_calling` (`academic_id`, `branch_id`, `calling_enabled`) VALUES
(1, 1, 0);

-- pickup_settings: 1 rows
INSERT INTO `pickup_settings` (`id`, `academic_id`, `repeat_count`, `cooldown_seconds`, `calling_enabled`) VALUES
(1, 1, 2, 30, 0);

-- position: 40 rows
INSERT INTO `position` (`id`, `position`, `translate`, `departmentId`) VALUES
(1, 'Chairman of Board of Directors', 'ប្រធានក្រុមប្រឹក្សាភិបាល', 1),
(2, 'Member of Board of Director', 'សមាជិកក្រុមប្រឹក្សាភិបាល', 1),
(3, 'Director', 'នាយក', 2),
(4, 'Vice Director', 'នាយករង', 2),
(5, 'Senior Advisor of Academy', 'ទីប្រឹក្សាជាន់ខ្ពស់ផ្នែកសិក្សាធិការ', 2),
(6, 'Senior Advisor of Curriculum Development', 'ទីប្រឹក្សាជាន់ខ្ពស់ផ្នែកអភិវឌ្ឍកម្មវិធីសិក្សា', 2),
(7, 'Head of HR', 'ប្រធានផ្នែកធនធានមនុស្ស', 3),
(8, 'Training Coordinator', 'ប្រធានផ្នែកបណ្តុះបណ្តាល', 3),
(9, 'Assistant to HR', 'ជំនួយការធនធានមនុស្ស', 3),
(10, 'Head of Admin', 'ប្រធានផ្នែករដ្ឋបាល', 4),
(11, 'Admin Assistant', 'ជំនួយការរដ្ឋបាល', 4),
(13, 'Cleaner and Gardener', 'អ្នកសម្អាត និងថែទាំសួន', 4),
(14, 'Security Guard-Gardener-Cleaner', 'សន្តិសុខ ថែសួន និងសម្អាត', 4),
(15, 'Driver-Security Guards', 'អ្នកបើកបរ និងសន្តិសុខ', 4),
(16, 'Driver-Security Guards-Cleaner', 'អ្នកបើកបរ សន្តិសុខ និងសម្អាត', 4),
(17, 'Security Guards-Cleaner', 'សន្តិសុខអនាម័យ', 4),
(18, 'Gardener', 'មន្ត្រីផ្នែកកសិកម្ម', 4),
(19, 'Head of Finance', 'ប្រធានផ្នែកហិរញ្ញវត្តុ', 5),
(20, 'Cashier', 'បេឡាធិការ/បេឡាធិការិនី', 5),
(21, 'Accountant', 'គណនេយ្យករ', 5),
(22, 'Financial assistant', 'ជំនួយការហិរញ្ញវត្ថុ', 5),
(23, 'Accounting Assistant', 'ជំនួយការគណនេយ្យ', 5),
(24, 'Head of IT', 'ប្រធានព័ត៌មានវិទ្យា', 6),
(25, 'Digital Marketer', 'មន្ត្រីម៉ាឃីតធីងឌីជីថល', 6),
(26, 'IT Supporter', 'ជំនួយការព័ត៌មានវិទ្យា', 6),
(27, 'Camera Woman', 'មន្ត្រីផ្នែកថតរូប​ (ស្រី)', 6),
(28, 'Camera Man', 'មន្ត្រីផ្នែកថតរូប (ប្រុស)', 6),
(29, 'Admin & Program Supporter', 'ជំនួយការរដ្ឋបាល និងដំណើរការកម្មវិធី', 7),
(30, 'Head of Academy', 'ប្រធានសិក្សាធិការ', 8),
(31, 'Head of Teacher', 'ប្រធានគ្រូ', 8),
(32, 'Academic Assistant', 'ជំនួយការសិក្សាធិការ', 8),
(33, 'Head Teacher Assistant', 'ជំំនួយការប្រធានគ្រូ', 8),
(34, 'Teacher', 'គ្រូបង្រៀន', 8),
(35, 'Chinese Teacher', 'គ្រូបង្រៀនភាសាចិន', 8),
(36, 'English Teacher', 'គ្រូបង្រៀនភាសាអង់គ្លេស', 8),
(37, 'Teacher Assistant', 'ជំនួយការគ្រូ', 8),
(38, 'Internship Teacher', 'គ្រូបង្រៀនហាត់ការ', 8),
(39, 'Head of Part Time Teacher', 'ប្រធានគ្រូបង្រៀនក្រៅម៉ោង', 9),
(40, 'Assistant to Head of Part time Teacher', 'ជំនួយការប្រធានគ្រូបង្រៀនក្រៅម៉ោង', 9),
(41, 'Part time Teacher', 'គ្រូបង្រៀនក្រៅម៉ោង', 9);

-- price_visibility_settings: 1 rows
INSERT INTO `price_visibility_settings` (`id`, `branch_id`, `program_id`, `show_monthly`, `show_quarter`, `show_semester`, `show_oneyear`) VALUES
(1, NULL, NULL, 1, 1, 1, 1);

-- program: 3 rows
INSERT INTO `program` (`id`, `program_name`, `program_name_us`, `mark_type`, `short_code`, `academic_id`, `report_status`, `head_user_id`, `time_report`, `created_by`, `updated_by`, `noted`) VALUES
(1, 'ជាតិពិសេស ចំណេះទូទៅភាសាខ្មែរ (UNP)', 'Unique National Program (UNP)', 'kh', 'UNP', 1, 'no', 1, '16:16:15', 1, 1, 'ចំណេះដឹងទូទៅភាសាខ្មែរ'),
(2, 'WAC', 'WAC', 'en', 'WAC', 1, 'no', 1, '16:21:15', 1, 1, 'Western Australian'),
(3, 'ភាសាអង់គ្លេសអន្តរជាតិ (IEP)', 'International English Program (IEP)', 'iep', 'IEP', 1, 'no', 1, '16:26:15', 1, 1, '');

-- results_top_students_display_settings: 1 rows
INSERT INTO `results_top_students_display_settings` (`id`, `avatar_chip_mode`, `hide_section`, `hide_medals_section`) VALUES
(1, 'grade', 0, 0);

-- role_permissions: 213 rows
INSERT INTO `role_permissions` (`id`, `role_id`, `permission_id`) VALUES
(32, 2, 1),
(33, 2, 25),
(34, 2, 3),
(35, 2, 4),
(36, 2, 5),
(37, 2, 6),
(38, 2, 7),
(39, 2, 8),
(40, 2, 9),
(41, 2, 10),
(42, 2, 11),
(120, 12, 13),
(121, 13, 14),
(126, 2, 26),
(248, 5, 2),
(249, 5, 22),
(250, 5, 3),
(251, 5, 26),
(252, 5, 9),
(253, 5, 17),
(254, 5, 30),
(255, 5, 21),
(256, 5, 1),
(257, 5, 5),
(258, 5, 36),
(259, 6, 10),
(260, 6, 6),
(261, 6, 4),
(262, 6, 11),
(263, 6, 7),
(264, 6, 5),
(265, 6, 36),
(291, 9, 11),
(292, 9, 9),
(293, 9, 36),
(294, 8, 8),
(295, 8, 11),
(296, 8, 36),
(297, 7, 10),
(298, 7, 6),
(299, 7, 7),
(300, 7, 5),
(301, 7, 37),
(302, 7, 36),
(303, 4, 2),
(304, 4, 6),
(305, 4, 22),
(306, 4, 11),
(307, 4, 3),
(308, 4, 29),
(309, 4, 26),
(310, 4, 25),
(311, 4, 9),
(312, 4, 30),
(313, 4, 21),
(314, 4, 1),
(315, 4, 5),
(316, 4, 36),
(317, 4, 37),
(368, 3, 10),
(369, 3, 2),
(370, 3, 6),
(371, 3, 37),
(372, 3, 36),
(373, 3, 4),
(374, 3, 8),
(375, 3, 11),
(376, 3, 3),
(377, 3, 7),
(378, 3, 9),
(379, 3, 5),
(380, 3, 40),
(381, 3, 38),
(382, 3, 39),
(468, 3, 41),
(469, 3, 42),
(470, 3, 43),
(471, 1, 14),
(472, 1, 10),
(473, 1, 18),
(474, 1, 2),
(475, 1, 6),
(476, 1, 31),
(477, 1, 34),
(478, 1, 37),
(479, 1, 36),
(480, 1, 16),
(481, 1, 12),
(482, 1, 20),
(483, 1, 28),
(484, 1, 4),
(485, 1, 8),
(486, 1, 40),
(487, 1, 38),
(488, 1, 39),
(489, 1, 22),
(490, 1, 24),
(491, 1, 23),
(492, 1, 15),
(493, 1, 11);
INSERT INTO `role_permissions` (`id`, `role_id`, `permission_id`) VALUES
(494, 1, 19),
(495, 1, 35),
(496, 1, 3),
(497, 1, 7),
(498, 1, 32),
(499, 1, 29),
(500, 1, 26),
(501, 1, 25),
(502, 1, 13),
(503, 1, 9),
(504, 1, 17),
(505, 1, 30),
(506, 1, 21),
(507, 1, 1),
(508, 1, 5),
(509, 1, 43),
(510, 1, 42),
(511, 1, 41),
(512, 1, 44),
(513, 1, 45),
(514, 1, 46),
(515, 1, 47),
(516, 1, 48),
(517, 1, 49),
(518, 1, 50),
(519, 1, 51),
(520, 1, 52),
(521, 1, 53),
(522, 1, 54),
(523, 1, 55),
(524, 1, 56),
(525, 1, 57),
(526, 1, 58),
(527, 1, 59),
(528, 1, 60),
(529, 1, 61),
(530, 1, 62),
(531, 1, 63),
(532, 1, 64),
(533, 1, 65),
(534, 1, 66),
(535, 1, 67),
(536, 1, 68),
(537, 1, 69),
(538, 1, 70),
(539, 1, 71),
(540, 1, 72),
(541, 1, 73),
(542, 1, 74),
(543, 1, 75),
(544, 1, 76),
(545, 1, 77),
(546, 1, 78),
(547, 1, 79),
(548, 1, 80),
(549, 1, 81),
(550, 1, 82),
(551, 1, 83),
(552, 1, 84),
(553, 1, 85),
(554, 1, 86),
(555, 1, 87),
(556, 1, 88),
(557, 1, 89),
(558, 1, 90),
(559, 1, 91),
(560, 1, 92),
(561, 1, 93),
(562, 1, 94),
(563, 1, 95),
(564, 1, 96),
(565, 1, 97),
(566, 1, 98),
(567, 1, 99),
(568, 1, 100),
(569, 1, 101),
(570, 1, 102),
(571, 1, 103),
(572, 1, 104),
(573, 1, 105),
(574, 1, 106),
(575, 1, 107),
(576, 1, 108),
(577, 1, 109),
(578, 1, 27),
(579, 2, 64),
(580, 3, 64),
(581, 4, 64),
(582, 5, 64),
(583, 6, 64),
(584, 7, 64),
(585, 8, 64),
(586, 9, 64),
(587, 10, 64),
(588, 10, 36),
(589, 10, 65),
(590, 10, 66),
(591, 10, 68),
(592, 10, 2),
(593, 10, 74);
INSERT INTO `role_permissions` (`id`, `role_id`, `permission_id`) VALUES
(594, 10, 75),
(595, 10, 76),
(596, 10, 82),
(597, 10, 44),
(598, 10, 45),
(599, 10, 47),
(600, 10, 48),
(601, 11, 64),
(602, 11, 36),
(603, 12, 64),
(604, 13, 64),
(605, 1, 110),
(606, 3, 110);

-- roles: 13 rows
INSERT INTO `roles` (`id`, `role_name`) VALUES
(1, 'Super Admin'),
(2, 'Teacher'),
(3, 'Admin'),
(4, 'Accountant'),
(5, 'Reception'),
(6, 'Viewer'),
(7, 'Principal'),
(8, 'Counselor'),
(9, 'Librarian'),
(10, 'Registrar'),
(11, 'ITSupport'),
(12, 'Parent'),
(13, 'Student');

-- settings: 1 rows
INSERT INTO `settings` (`id`, `enterpriseName`, `enterpriseType`, `eProvince`, `eDistrict`, `eCommune`, `eVillage`, `enterpriseAddress`, `ownerKname`, `ownerEname`, `ownerGender`, `ownerNationality`, `isForeigner`, `prefixid`, `suffix`, `digit_number`, `follow_type`, `academicid`, `startid`, `status_fixedexchange`, `default_exchange`, `telegrambot`, `parent_bot_token`, `chat_id`, `time_report`, `report_chat_id`, `report_status`, `skip_sat`, `skip_sun`, `time_allow_start`, `time_allow_end`, `marks_extraday`, `notify_parents`, `system_logo`, `system_name`, `secret_pass`, `image_header`, `facebook_url`, `telegram_url`, `youtube_url`, `instagram_url`, `tiktok_url`, `active_storage_provider`, `cloudinary_cloud_name`, `cloudinary_api_key`, `cloudinary_api_secret`, `aws_access_key_id`, `aws_secret_access_key`, `aws_region_name`, `aws_bucket_name`, `firebase_storage_bucket`, `firebase_service_account_json`, `enable_schedule_reminders`, `ota_updates_enabled`, `phone_conflict_lock_enabled`) VALUES
(1, 'Kampul SIS', 'School', '', '', '', '', '', 'Super Admin', 'Super Admin', '', '', 0, 'KMP-', '', 6, 'settings', 1, 1, 'yes', 4100, '', '', '', NULL, '', 'no', 'no', 'no', '06:00:00', '18:00:00', '5', 'no', '', 'Kampul SIS', '', '', NULL, NULL, NULL, NULL, NULL, 'local', '', '', '', '', '', '', '', '', NULL, 'no', 1, NULL);

-- shift: 2 rows
INSERT INTO `shift` (`id`, `shift_name`, `shift_name_en`, `start_at`, `end_at`, `report_status`, `send_report_at`, `weeken_send`) VALUES
(1, 'វេនព្រឹក (AM)', 'Morning (AM)', '7:15:00', '11:00:00', 'no', '8:15:00', 'no'),
(2, 'វេនរសៀល (PM)', 'Afternoon (PM)', '12:00:00', '18:00:00', 'no', '14:16:00', 'no');

-- status: 5 rows
INSERT INTO `status` (`id`, `status`) VALUES
(1, 'Active'),
(2, 'Inactive'),
(3, 'Suspended'),
(4, 'Finished'),
(5, 'Banned');

-- subjects: 43 rows
INSERT INTO `subjects` (`id`, `subject_name`, `subject_name_us`, `program_id`, `academic_id`, `created_by`, `updated_by`, `noted`, `short_code`, `updated_at`, `created_at`) VALUES
(1, 'ភាសាខ្មែរ', 'Khmer Language', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(2, 'សរសេរតាមអាន', 'Dictation', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(3, 'គណិតវិទ្យា', 'Mathematics', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(4, 'ប៉ាម៉ាគិតលេខរហ័ស', 'Kampul SIS Programs', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(5, 'វិទ្យាសាស្ត្រអនុវត្ត', 'Science', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(6, 'សិក្សាសង្គម', 'Social Studies', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(7, 'កុំព្យូទ័រ', 'ICT', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(8, 'សិល្បៈ អប់រំកាយ កីឡា', 'Art, P.E & Sports', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(9, 'គំនូរ & ហត្ថកម្ម', 'Drawing & Handicraft', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(10, 'ភាសាអង់គ្លេស', 'English', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(11, 'អប់រំសុខភាព', 'Health Education', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(13, 'រូបវិទ្យា', 'Physics', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(14, 'គីមីវិទ្យា', 'Chemistry', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(15, 'ជីវវិទ្យា', 'Biology', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(16, 'ផែនដីវិទ្យា', 'Earth Science', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(17, 'សីលធម៌-ពលរដ្ឋវិជ្ជា', 'Moral Civics', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(18, 'ភូមិវិទ្យា', 'Geography', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(19, 'ប្រវត្តិវិទ្យា', 'History', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(20, 'គេហវិជ្ជា', 'Home Science', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(21, 'អប់រំកាយ និងកីឡា', 'P.E and Sports', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(24, 'អប់រំសុខភាព', 'Health Education', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(25, 'បុរេសំណេរ', 'Pre-Writing', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(26, 'បុរេគណិត', 'Pre-Math', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(27, 'ចិត្តចលភាព', 'Physical Education', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(28, 'វិទ្យាសាស្ដ្រ-សិក្សាសង្គម', 'Social and Science', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(29, 'អារម្មណ៍ បញ្ញា សង្គម', 'Emotional and Cognitive', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(30, 'អប់រំសុខភាព-អនាម័យ', 'Health- Hygiene', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(31, 'Eng', NULL, 3, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(32, 'Math', NULL, 3, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(33, 'HASS', '', 3, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(34, 'Science', NULL, 3, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(35, 'PE', '', 3, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(36, 'Art', NULL, 3, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(37, 'DT', NULL, 3, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(38, 'English', '', 2, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(39, 'Math', NULL, 2, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(40, 'HASS', '', 2, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(41, 'Science', NULL, 2, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(42, 'HPE', '', 2, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(43, 'The Arts', '', 2, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(44, 'Technologies', '', 2, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(49, 'សិក្សាបែបគម្រោង/មេឌៀ', 'Projects/Media', 1, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
(52, 'Techcademy', 'Techcademy', 2, 1, 1, 1, '', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00');

-- subjects_group: 85 rows
INSERT INTO `subjects_group` (`id`, `grade_group_id`, `program_id`, `subject_id`, `full_marks`, `calculate_marks`, `academic_id`, `created_by`, `updated_by`, `noted`) VALUES
(130, 29, 1, 1, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(131, 29, 1, 2, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(132, 29, 1, 3, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(133, 29, 1, 4, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(134, 29, 1, 5, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(135, 29, 1, 6, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(136, 29, 1, 7, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(137, 29, 1, 8, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(138, 29, 1, 9, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(139, 29, 1, 10, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(140, 29, 1, 11, '10.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(141, 28, 1, 25, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(142, 28, 1, 26, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(143, 28, 1, 27, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(144, 28, 1, 28, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(145, 28, 1, 29, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(146, 28, 1, 30, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(147, 32, 1, 1, '150.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(148, 32, 1, 3, '150.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(149, 32, 1, 13, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(150, 32, 1, 14, '37.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(151, 32, 1, 15, '38.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(152, 32, 1, 16, '25.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(153, 32, 1, 17, '38.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(154, 32, 1, 18, '38.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(155, 32, 1, 19, '37.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(156, 32, 1, 20, '37.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(157, 32, 1, 10, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(158, 32, 1, 21, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(159, 32, 1, 49, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(160, 32, 1, 7, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(161, 32, 1, 24, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(162, 30, 1, 1, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(163, 30, 1, 3, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(164, 30, 1, 13, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(165, 30, 1, 14, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(166, 30, 1, 15, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(167, 30, 1, 16, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(168, 30, 1, 17, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(169, 30, 1, 18, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(170, 30, 1, 19, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(171, 30, 1, 20, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(172, 30, 1, 10, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(173, 30, 1, 21, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(174, 30, 1, 24, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(175, 30, 1, 7, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(176, 30, 1, 49, '50.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(177, 31, 1, 1, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(178, 31, 1, 3, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(179, 31, 1, 13, '35.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(180, 31, 1, 14, '25.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(181, 31, 1, 15, '35.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(182, 31, 1, 16, '25.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(183, 31, 1, 17, '35.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(184, 31, 1, 10, '50.00', '50.00', 1, 1, 1, 'Cloned from academic 2'),
(185, 31, 1, 18, '32.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(186, 31, 1, 19, '33.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(187, 33, 3, 31, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(188, 33, 3, 32, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(189, 33, 3, 33, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(190, 33, 3, 34, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(191, 33, 3, 35, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(192, 33, 3, 36, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(193, 33, 3, 37, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(194, 36, 2, 38, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(195, 36, 2, 39, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(196, 36, 2, 40, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(197, 36, 2, 41, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(198, 36, 2, 42, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(199, 36, 2, 43, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(200, 36, 2, 44, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(201, 34, 2, 38, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(202, 34, 2, 39, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(203, 34, 2, 40, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(204, 34, 2, 41, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(205, 34, 2, 42, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(206, 34, 2, 43, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(207, 34, 2, 44, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(208, 35, 2, 38, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(209, 35, 2, 39, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(210, 35, 2, 40, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(211, 35, 2, 41, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(212, 35, 2, 42, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(213, 35, 2, 43, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2'),
(214, 35, 2, 44, '100.00', '100.00', 1, 1, 1, 'Cloned from academic 2');

-- units: 32 rows
INSERT INTO `units` (`id`, `name`) VALUES
(1, 'ប្រអប់'),
(2, 'កេស'),
(3, 'ក្បាល'),
(4, 'ដុំ'),
(5, 'ធុង'),
(6, 'ឯកតា'),
(7, 'ប្រអប់'),
(8, 'កញ្ចប់'),
(9, 'ញ៉ុង'),
(10, 'កាបូប'),
(11, 'ដប'),
(12, 'កំប៉ុង'),
(13, 'ការទុន'),
(14, 'ប្រអប់ធំ'),
(15, 'លីត្រ'),
(16, 'មីលីលីត្រ'),
(17, 'គីឡូក្រាម'),
(18, 'ក្រាម'),
(19, 'ម៉ែត្រ'),
(20, 'សង់ទីម៉ែត្រ'),
(21, 'ដុសិន'),
(22, 'សំណុំ'),
(23, 'គូ'),
(24, 'មូល'),
(25, 'មួក'),
(26, 'រមៀល'),
(27, 'ក្បាល'),
(28, 'ឈុត'),
(29, 'កញ្ចប់'),
(30, 'បាច់ធំ'),
(31, 'សន្លឹក'),
(32, 'បំពង់');

-- attendance_system_settings: 1 rows
INSERT INTO `attendance_system_settings` (`id`, `require_location`, `block_mock_location`, `block_developer_options`, `allowed_ip_ranges`, `allow_early_clock_in_mins`, `allow_late_clock_out_mins`, `late_grace_minutes`, `per_session_early_clock_in_mins`, `min_minutes_before_checkout`, `allow_early_leave_mins`, `allow_makeup_missing_sessions`, `notify_enable_before`, `notify_minutes_before`, `notify_enable_after`, `notify_minutes_after`, `notify_enable_before_checkout`, `notify_minutes_before_checkout`, `notify_enable_after_checkout`, `notify_minutes_after_checkout`, `session_transition_wait_mins`) VALUES
(1, 0, 1, 0, NULL, 30, 60, 15, NULL, 0, 0, 0, 0, '[]', 0, '[]', 0, '[]', 0, '[]', 0);

-- certificate_settings: 1 rows
INSERT INTO `certificate_settings` (`id`, `academic_id`, `prefix`, `surfix`, `digit`, `year`, `orientation`) VALUES
(1, 1, 'KMP-', '', 6, '2026', 'landscape');

-- telegram_attendance_settings: 1 rows
INSERT INTO `telegram_attendance_settings` (`id`, `bot_token`, `chat_id`, `enabled`, `notify_leave_requests`, `notify_leave_decisions`, `leave_routing_mode`, `leave_chat_id`, `branch_routing_mode`) VALUES
(1, NULL, NULL, 0, 0, 0, 'combined', NULL, 'all');

SET FOREIGN_KEY_CHECKS = 1;
