# News video rollout and rollback

## Requirements

- FFmpeg and FFprobe should be installed on the API host. Uploaded MP4 files
  still work without FFmpeg, but MOV/M4V/WebM conversion and automatic
  thumbnails require it.
- `NEWS_VIDEO_MAX_UPLOAD_MB` defaults to `250`.
- Local video files are served with HTTP byte-range support. Cloudinary, S3,
  and Firebase provide their own range delivery.

## Safe rollout

1. Deploy the API first. Startup migration 50 adds nullable video metadata and
   defaults every existing news row to `media_type = 'image'`.
2. Confirm `GET /api/v1/news/public` still returns existing photo news.
3. Deploy the Flutter app with the new dependencies.
4. Publish a private/test-audience uploaded video and a YouTube video.
5. Verify thumbnail-first playback, muted home autoplay, sound opt-in, and the
   home-to-detail playback handoff.

Old app builds ignore the additional JSON fields. New app builds treat a
response with no media fields as an image post.

## Fast operational rollback

1. Set API environment variable `NEWS_VIDEO_ENABLED=false`. This blocks new
   video uploads/publishing without affecting existing photo news.
2. Build the Flutter app with:

   ```sh
   flutter build apk --dart-define=NEWS_VIDEO_ENABLED=false
   ```

   Use the same define for the iOS build. Video posts then render as thumbnails.
3. If code rollback is required, deploy the prior API/app versions. The added
   database columns are harmless and can remain in place.

## Full schema rollback

Only after the previous API version is running, execute:

```sh
mysql -u USER -p DATABASE < migrations/rollback_news_video_media.sql
```

That script drops only the five video columns. It does not change news rows,
photo covers, or gallery images. Uploaded video files should be retained until
the rollback has been verified, then removed through the normal admin delete
flow or storage lifecycle policy.
