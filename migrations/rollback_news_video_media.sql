-- Emergency rollback for migration 50.
-- First set NEWS_VIDEO_ENABLED=false and deploy the previous app/API version.
-- This removes only the five new columns; photo news and gallery data are untouched.
ALTER TABLE news DROP COLUMN video_original_url;
ALTER TABLE news DROP COLUMN video_duration_seconds;
ALTER TABLE news DROP COLUMN video_thumbnail_url;
ALTER TABLE news DROP COLUMN video_url;
ALTER TABLE news DROP COLUMN video_source;
ALTER TABLE news DROP COLUMN media_type;
