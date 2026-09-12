-- Disable new imports before running:
-- NEWS_YOUTUBE_MIRRORING_ENABLED=false
--
-- Restore every mirrored YouTube post to its original embed URL. Local MP4
-- files are intentionally retained so this rollback is recoverable.
UPDATE news
SET video_source = 'youtube',
    video_url = video_original_url,
    video_duration_seconds = NULL
WHERE media_type = 'video'
  AND video_original_url IS NOT NULL
  AND video_original_url <> '';

ALTER TABLE news DROP COLUMN video_original_url;
