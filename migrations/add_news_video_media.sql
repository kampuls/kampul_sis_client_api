-- Backward-compatible news video rollout.
-- Existing records stay image posts because media_type defaults to 'image'.
ALTER TABLE news ADD COLUMN media_type VARCHAR(20) NOT NULL DEFAULT 'image';
ALTER TABLE news ADD COLUMN video_source VARCHAR(20) NULL;
ALTER TABLE news ADD COLUMN video_url VARCHAR(1000) NULL;
ALTER TABLE news ADD COLUMN video_thumbnail_url VARCHAR(1000) NULL;
ALTER TABLE news ADD COLUMN video_duration_seconds INT NULL;
