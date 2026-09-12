# Real-time Sync: Current Behavior

## How It Works Now

✅ **API Changes** → Real-time sync works
- When you mark attendance through the Flutter app
- When you update data through FastAPI endpoints
- WebSocket broadcasts are sent immediately
- All connected clients receive updates instantly

❌ **Direct MySQL Changes** → No real-time sync
- If you update the database directly (SQL, phpMyAdmin, etc.)
- WebSocket broadcasts are NOT triggered
- Changes will appear after:
  - Cache expires (2-15 minutes depending on data type)
  - User refreshes the page
  - User navigates away and comes back

## Why?

The current implementation broadcasts updates from the **API layer**, not from the database. This is by design because:

1. **API validation**: Changes go through business logic and validation
2. **Security**: Only authorized users can make changes
3. **Performance**: No need to monitor database changes constantly

## Solutions if You Need Direct MySQL Changes to Sync

### Option 1: Always Use API (Recommended) ✅
- **Best practice**: Always make changes through the API
- All changes will sync in real-time
- Maintains data integrity and security

### Option 2: MySQL Triggers + Background Service
Create a background service that monitors database changes:

```python
# This would require additional setup
# Monitor MySQL binlog or use triggers
# Then broadcast via WebSocket
```

### Option 3: Polling Fallback (Current Cache Behavior)
- Cache expires after 2-15 minutes
- Next API call will fetch fresh data
- Not real-time, but eventually consistent

### Option 4: Manual Cache Invalidation
If you make direct MySQL changes, you can manually refresh:
- Pull to refresh in the app
- Navigate away and come back
- Wait for cache to expire

## Current Cache TTL (Time To Live)

- Student lists: **3 minutes**
- Individual students: **5 minutes**
- Attendance settings: **10 minutes**
- Branches/Programs/Shifts: **15 minutes**
- Attendance data: **2 minutes**

After cache expires, fresh data is fetched from the database.
