# Ads/Banner System Design

## Overview

This document describes the sliding ads/banner system for the home screen, including database structure, image storage, and implementation details.

## Database Schema

### 1. `ads` Table

Stores all advertisement/banner information.

```sql
CREATE TABLE `ads` (
  `id` INT(11) NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(255) NOT NULL COMMENT 'Ad title (e.g., "New Academic Year Registration")',
  `subtitle` VARCHAR(255) DEFAULT NULL COMMENT 'Short subtitle or tagline',
  `description` TEXT DEFAULT NULL COMMENT 'Full description shown in detail screen',
  `image_url` VARCHAR(500) NOT NULL COMMENT 'Path to image file (e.g., "/uploads/ads/banner_001.jpg")',
  `image_path` VARCHAR(500) DEFAULT NULL COMMENT 'Full server path if needed',
  `ad_type` VARCHAR(50) NOT NULL DEFAULT 'general' COMMENT 'Type: general, registration, event, announcement, promotion',
  `action_type` VARCHAR(50) DEFAULT NULL COMMENT 'Action: register, navigate, external_link, none',
  `action_data` JSON DEFAULT NULL COMMENT 'Action parameters (e.g., {"route": "registration", "params": {...}})',
  `button_text` VARCHAR(100) DEFAULT NULL COMMENT 'Button text (e.g., "Register Now", "Learn More")',
  `button_color` VARCHAR(20) DEFAULT '#1976D2' COMMENT 'Button color in hex',
  `target_audience` VARCHAR(50) DEFAULT 'all' COMMENT 'all, teachers, students, parents, staff',
  `start_date` DATETIME DEFAULT NULL COMMENT 'When ad should start showing',
  `end_date` DATETIME DEFAULT NULL COMMENT 'When ad should stop showing',
  `is_active` TINYINT(1) DEFAULT 1 COMMENT '1 = active, 0 = inactive',
  `display_order` INT(11) DEFAULT 0 COMMENT 'Order for display (lower = first)',
  `click_count` INT(11) DEFAULT 0 COMMENT 'Number of times ad was clicked',
  `view_count` INT(11) DEFAULT 0 COMMENT 'Number of times ad was viewed',
  `created_by` INT(11) DEFAULT NULL COMMENT 'User ID who created the ad',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `academic_id` INT(11) DEFAULT NULL COMMENT 'Filter by academic year',
  `branch_id` INT(11) DEFAULT NULL COMMENT 'Filter by branch (NULL = all branches)',
  PRIMARY KEY (`id`),
  KEY `idx_active` (`is_active`, `start_date`, `end_date`),
  KEY `idx_display_order` (`display_order`),
  KEY `idx_academic` (`academic_id`),
  KEY `idx_branch` (`branch_id`),
  KEY `idx_type` (`ad_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2. `ad_clicks` Table (Optional - for analytics)

Track ad clicks for analytics.

```sql
CREATE TABLE `ad_clicks` (
  `id` INT(11) NOT NULL AUTO_INCREMENT,
  `ad_id` INT(11) NOT NULL,
  `user_id` INT(11) DEFAULT NULL COMMENT 'User who clicked (if logged in)',
  `user_type` VARCHAR(50) DEFAULT NULL COMMENT 'teacher, student, parent, guest',
  `clicked_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `device_info` VARCHAR(255) DEFAULT NULL COMMENT 'Device type, OS, etc.',
  PRIMARY KEY (`id`),
  KEY `idx_ad` (`ad_id`),
  KEY `idx_user` (`user_id`),
  KEY `idx_date` (`clicked_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## Image Storage

### Image Size Recommendations

**Recommended Dimensions:**
- **Optimal Size**: **800 x 320 pixels** (2.5:1 aspect ratio)
- **Minimum Size**: 400 x 160 pixels (for basic quality)
- **High-DPI Support**: 1600 x 640 pixels (for Retina/2x displays)
- **Ultra High-DPI**: 2400 x 960 pixels (for 3x displays)

**Aspect Ratio:** 2.5:1 (width:height)

**Why these dimensions?**
- The Flutter app displays banners at **160px height** with full width
- Images use `BoxFit.cover` which crops to fill the container
- Cache dimensions in Flutter are set to 800x320 for optimal memory usage
- 2.5:1 aspect ratio ensures images look good on all mobile screen sizes

**File Requirements:**
- **Maximum File Size**: 5MB (enforced by API)
- **Allowed Formats**: JPEG, PNG, WebP
- **Recommended Format**: JPEG (for photos) or PNG (for graphics with text)
- **Compression**: Use 80-90% quality for JPEG to balance file size and quality

**Design Tips:**
- Keep important content (text, logos) in the center 60% of the image
- Avoid placing critical elements near the edges (may be cropped on different screen sizes)
- Use high contrast for text overlays
- Test on both portrait and landscape orientations

### Option 1: Server File System (Recommended)

- **Location**: `pama_api/uploads/ads/`
- **Naming**: `ad_{uuid}.jpg` or `ad_{uuid}.png`
- **URL Format**: `https://your-api-domain.com/uploads/ads/ad_xxx.jpg`
- **Access**: Serve via static file serving (nginx or FastAPI static files)

### Option 2: Cloud Storage (AWS S3, Google Cloud Storage)

- Store images in cloud storage
- Save only the URL in database
- Better for scalability

### Directory Structure

```
pama_api/
├── uploads/
│   ├── ads/
│   │   ├── ad_1_1699123456.jpg
│   │   ├── ad_2_1699123457.png
│   │   └── ...
│   └── thumbnails/  (optional - for smaller previews)
│       └── ads/
```

## Ad Types and Actions

### Ad Types

- `general` - General announcements
- `registration` - Registration for academic year, events, etc.
- `event` - School events, meetings
- `announcement` - Important announcements
- `promotion` - Promotional content

### Action Types

- `register` - Navigate to registration screen
- `navigate` - Navigate to internal screen (specify route in action_data)
- `external_link` - Open external URL
- `none` - Just show detail screen

### Action Data Examples

**Registration Action:**

```json
{
  "type": "register",
  "route": "academic_registration",
  "params": {
    "academic_id": 1,
    "form_type": "new_student"
  }
}
```

**Navigation Action:**

```json
{
  "type": "navigate",
  "route": "results",
  "params": {
    "class_id": 5
  }
}
```

**External Link:**

```json
{
  "type": "external_link",
  "url": "https://example.com/event-details"
}
```

## API Endpoints Needed

### 1. Get Active Ads

```
GET /api/v1/ads/
Query params:
  - academic_id (optional)
  - branch_id (optional)
  - user_type (optional) - filter by target_audience
  - limit (optional) - default 10
```

### 2. Get Ad Detail

```
GET /api/v1/ads/{ad_id}
```

### 3. Create Ad (Admin)

```
POST /api/v1/ads/
Body: FormData with image file
```

### 4. Update Ad (Admin)

```
PUT /api/v1/ads/{ad_id}
Body: FormData with optional image file
```

### 5. Delete Ad (Admin)

```
DELETE /api/v1/ads/{ad_id}
```

### 6. Track Ad Click

```
POST /api/v1/ads/{ad_id}/click
Body: { "user_id": 123, "user_type": "teacher" }
```

### 7. Track Ad View

```
POST /api/v1/ads/{ad_id}/view
Body: { "user_id": 123, "user_type": "teacher" }
```

## Implementation Steps

### Backend (Python/FastAPI)

1. Create `ads` model in `app/models/`
2. Create `ads.py` API router in `app/api/v1/`
3. Set up file upload handling
4. Configure static file serving for images
5. Implement CRUD operations
6. Add click/view tracking

### Frontend (Flutter)

1. Create `Ad` model
2. Create `AdsService` to fetch ads
3. Update `HomeScreen` to fetch and display ads
4. Create `AdDetailScreen` for ad details
5. Implement click tracking
6. Handle different action types

## Example Data

```sql
INSERT INTO `ads` (
  `title`, `subtitle`, `description`, `image_url`,
  `ad_type`, `action_type`, `action_data`, `button_text`,
  `target_audience`, `is_active`, `display_order`
) VALUES (
  'New Academic Year Registration',
  'Register Now for 2024-2025',
  'Join us for the new academic year! Registration is now open for all students. Click below to register.',
  '/uploads/ads/ad_1_1699123456.jpg',
  'registration',
  'register',
  '{"type": "register", "route": "academic_registration", "params": {"academic_id": 1}}',
  'Register Now',
  'all',
  1,
  1
);
```

## Security Considerations

1. **Image Upload Validation**

   - File type validation (jpg, png, webp)
   - File size limit (e.g., 5MB max)
   - Image dimension validation
   - Virus scanning (optional)

2. **Access Control**

   - Only admins can create/edit/delete ads
   - Users can only view active ads

3. **Rate Limiting**

   - Limit click/view tracking to prevent abuse

4. **Image Optimization**
   - Generate thumbnails for faster loading
   - Compress images on upload
