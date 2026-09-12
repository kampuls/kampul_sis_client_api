# Ads System Implementation Guide

## Quick Start

### 1. Database Setup

Run the migration to create the ads tables:

```bash
cd pama_api
alembic upgrade head
```

Or manually run the SQL from `alembic/versions/0002_create_ads_table.py`

### 2. Create Upload Directory

```bash
mkdir -p uploads/ads
```

### 3. Test the API

The API endpoints are now available at:
- `GET /api/v1/ads/` - Get active ads
- `GET /api/v1/ads/{ad_id}` - Get ad details
- `POST /api/v1/ads/` - Create ad (admin)
- `PUT /api/v1/ads/{ad_id}` - Update ad (admin)
- `DELETE /api/v1/ads/{ad_id}` - Delete ad (admin)
- `POST /api/v1/ads/{ad_id}/click` - Track click
- `POST /api/v1/ads/{ad_id}/view` - Track view

### 4. Example: Create an Ad via API

```bash
curl -X POST "http://localhost:8000/api/v1/ads/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "title=New Academic Year Registration" \
  -F "subtitle=Register Now for 2024-2025" \
  -F "description=Join us for the new academic year! Registration is now open." \
  -F "ad_type=registration" \
  -F "action_type=register" \
  -F "action_data={\"type\":\"register\",\"route\":\"academic_registration\"}" \
  -F "button_text=Register Now" \
  -F "button_color=#4CAF50" \
  -F "target_audience=all" \
  -F "display_order=1" \
  -F "image=@/path/to/image.jpg"
```

### 5. Example: Get Active Ads

```bash
curl -X GET "http://localhost:8000/api/v1/ads/?academic_id=1&user_type=teacher" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Database Tables

### `ads` Table
Stores all advertisement information including:
- Basic info (title, subtitle, description)
- Image URL and path
- Ad type and action configuration
- Display settings (order, dates, audience)
- Analytics (click_count, view_count)

### `ad_clicks` Table
Tracks individual clicks for analytics:
- Links clicks to specific ads
- Records user information
- Tracks device info and timestamps

## Image Storage

Images are stored in: `pama_api/uploads/ads/`

- Files are named: `ad_{uuid}.{ext}`
- Served at: `http://your-api-domain.com/uploads/ads/ad_xxx.jpg`
- Maximum file size: 5MB
- Allowed formats: JPEG, PNG, WebP

### Image Size Recommendations

**Recommended Dimensions:**
- **Optimal**: **800 x 320 pixels** (2.5:1 aspect ratio)
- **Minimum**: 400 x 160 pixels
- **High-DPI**: 1600 x 640 pixels (for Retina displays)
- **Ultra High-DPI**: 2400 x 960 pixels (for 3x displays)

**Why 800x320?**
- Flutter app displays banners at 160px height
- Cache dimensions are optimized for 800x320
- 2.5:1 aspect ratio works well on all mobile screen sizes
- Images use `BoxFit.cover` which crops to fill the container

**Design Guidelines:**
- Keep important content in the center 60% of the image
- Avoid placing critical elements near edges (may be cropped)
- Use high contrast for text overlays
- Test on different screen sizes and orientations

## Next Steps for Flutter App

1. Create `Ad` model in Flutter
2. Create `AdsService` to fetch ads from API
3. Update `HomeScreen` to display ads from API instead of hardcoded banners
4. Create `AdDetailScreen` to show ad details and handle actions
5. Implement click/view tracking

## Admin Panel (Future)

Consider creating an admin panel to:
- Upload and manage ads
- View analytics (clicks, views)
- Schedule ads (start/end dates)
- Target specific audiences

