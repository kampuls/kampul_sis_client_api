-- Migration: Add Telegram Attendance Settings table
-- Date: 2026-04-23
-- Description: Creates table for storing Telegram notification settings for attendance events

CREATE TABLE IF NOT EXISTS telegram_attendance_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    bot_token VARCHAR(500) NULL COMMENT 'Telegram bot token from BotFather',
    chat_id VARCHAR(100) NULL COMMENT 'Telegram chat ID (group or private)',
    enabled BOOLEAN DEFAULT FALSE COMMENT 'Enable/disable Telegram notifications',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation timestamp',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record last update timestamp'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS ix_telegram_attendance_settings_id ON telegram_attendance_settings(id);

-- Insert default row (disabled by default)
INSERT INTO telegram_attendance_settings (id, bot_token, chat_id, enabled)
SELECT 1, NULL, NULL, FALSE
WHERE NOT EXISTS (SELECT 1 FROM telegram_attendance_settings);
