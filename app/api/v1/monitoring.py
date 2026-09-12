"""
Performance monitoring endpoints.
Add these to your API to monitor cache, indexes, and query performance.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any

from ...core.database import get_db

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/cache-stats")
async def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics for all caches"""
    from ...services.query_cache import get_cache_stats as get_query_cache_stats
    from ...services.cache import permissions_cache, social_links_cache, settings_cache
    
    def get_cache_info(cache):
        now = __import__('time').time()
        active = sum(1 for _, exp in cache._cache.values() if exp > now)
        return {
            "total_entries": len(cache._cache),
            "active_entries": active,
            "expired_entries": len(cache._cache) - active,
            "max_size": cache._max_size,
            "ttl_seconds": cache._ttl,
        }
    
    return {
        "query_cache": get_query_cache_stats(),
        "permissions_cache": get_cache_info(permissions_cache),
        "social_links_cache": get_cache_info(social_links_cache),
        "settings_cache": get_cache_info(settings_cache),
    }


@router.get("/index-stats")
async def get_index_stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get database index statistics"""
    
    tables = ['daily_attendance', 'learning', 'students', 'marks_input', 
              'class_teachers', 'users', 'parents', 'holiday_tbl', 'forms']
    
    stats = {}
    
    for table in tables:
        try:
            # Get index count
            result = db.execute(text(f"""
                SELECT COUNT(DISTINCT INDEX_NAME) as index_count
                FROM information_schema.STATISTICS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = :table_name
            """), {"table_name": table}).fetchone()
            
            index_count = result[0] if result else 0
            
            # Get index names
            result = db.execute(text(f"""
                SELECT DISTINCT INDEX_NAME
                FROM information_schema.STATISTICS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = :table_name
                AND INDEX_NAME != 'PRIMARY'
            """), {"table_name": table}).fetchall()
            
            index_names = [row[0] for row in result] if result else []
            
            stats[table] = {
                "index_count": index_count,
                "index_names": index_names,
            }
        except Exception as e:
            stats[table] = {"error": str(e)}
    
    return stats


@router.get("/query-cache-stats")
async def get_detailed_query_cache_stats() -> Dict[str, Any]:
    """Get detailed query cache statistics"""
    from ...services.query_cache import query_cache
    
    now = __import__('time').time()
    
    # Analyze cache entries
    entries_by_prefix = {}
    for key in query_cache._cache.keys():
        prefix = key.split(":")[0] if ":" in key else "unknown"
        if prefix not in entries_by_prefix:
            entries_by_prefix[prefix] = {"total": 0, "active": 0}
        entries_by_prefix[prefix]["total"] += 1
        
        _, expires_at = query_cache._cache[key]
        if expires_at > now:
            entries_by_prefix[prefix]["active"] += 1
    
    return {
        "total_entries": len(query_cache._cache),
        "entries_by_prefix": entries_by_prefix,
        "default_ttl": query_cache._default_ttl,
    }


@router.get("/slow-queries")
async def get_slow_queries(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get slow query log statistics (requires MySQL slow query log enabled)"""
    
    try:
        # Check if slow query log is enabled
        result = db.execute(text("SHOW VARIABLES LIKE 'slow_query_log'")).fetchone()
        slow_query_enabled = result[1] == 'ON' if result else False
        
        result = db.execute(text("SHOW VARIABLES LIKE 'long_query_time'")).fetchone()
        long_query_time = float(result[1]) if result else 1.0
        
        return {
            "slow_query_enabled": slow_query_enabled,
            "long_query_time_seconds": long_query_time,
            "note": "Enable slow query log: SET GLOBAL slow_query_log = 'ON'"
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/connection-pool-stats")
async def get_connection_pool_stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get database connection pool statistics"""
    
    try:
        from ...core.database import engine
        
        pool = engine.pool
        pool_size = pool.size()
        checked_in = pool.checkedin()
        checked_out = pool.checkedout()
        overflow = pool.overflow()
        
        return {
            "pool_size": pool_size,
            "checked_in": checked_in,
            "checked_out": checked_out,
            "overflow": overflow,
            "utilization": f"{(checked_out / pool_size * 100):.1f}%" if pool_size > 0 else "N/A",
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/performance-summary")
async def get_performance_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get overall performance summary"""
    
    # Get all stats
    cache_stats = await get_cache_stats()
    index_stats = await get_index_stats(db)
    pool_stats = await get_connection_pool_stats(db)
    
    # Calculate health score
    health_score = 100
    issues = []
    
    # Check cache sizes
    for cache_name, stats in cache_stats.items():
        if isinstance(stats, dict) and "total_entries" in stats:
            if stats.get("total_entries", 0) > stats.get("max_size", 1000) * 0.9:
                health_score -= 10
                issues.append(f"{cache_name} cache is nearly full")
    
    # Check pool utilization
    if isinstance(pool_stats, dict):
        utilization = pool_stats.get("utilization", "0%")
        if isinstance(utilization, str) and float(utilization.replace("%", "")) > 80:
            health_score -= 15
            issues.append("Connection pool utilization is high")
    
    # Check index count
    critical_tables = ['daily_attendance', 'learning', 'students']
    for table in critical_tables:
        if table in index_stats:
            if index_stats[table].get("index_count", 0) < 2:
                health_score -= 10
                issues.append(f"Table {table} may need more indexes")
    
    return {
        "health_score": max(0, health_score),
        "status": "healthy" if health_score > 80 else "warning" if health_score > 50 else "critical",
        "issues": issues,
        "cache_stats": cache_stats,
        "index_stats": index_stats,
        "pool_stats": pool_stats,
    }
