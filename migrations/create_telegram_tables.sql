-- Migration: Create Telegram Attendance Settings Table
-- Run this on your production database

-- Drop existing tables to ensure clean schema
DROP TABLE IF EXISTS telegram_tracked_chats;
DROP TABLE IF EXISTS telegram_attendance_settings;

-- Create telegram_attendance_settings table with NOT NULL constraints
CREATE TABLE telegram_attendance_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bot_token VARCHAR(500) NULL COMMENT 'Telegram bot token from BotFather',
    chat_id VARCHAR(100) NULL COMMENT 'Telegram chat ID (group or private)',
    enabled BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Enable/disable Telegram notifications',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation timestamp',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record last update timestamp',
    INDEX idx_telegram_settings_id (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default row with ALL data populated (timestamps will auto-fill)
INSERT INTO telegram_attendance_settings (id, bot_token, chat_id, enabled)
VALUES (1, '8686190656:AAEl84Nkz7WwDe1SMn323iNV93BnIUeTvfw', NULL, FALSE);

-- Create telegram_tracked_chats table
CREATE TABLE telegram_tracked_chats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chat_id VARCHAR(100) NOT NULL UNIQUE COMMENT 'Telegram chat ID',
    chat_title VARCHAR(255) NOT NULL COMMENT 'Group/channel name',
    chat_type VARCHAR(50) NOT NULL COMMENT 'private, group, supergroup, channel',
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Bot still in chat',
    added_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When bot was added',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_chat_id (chat_id),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
