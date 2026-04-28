"""
Dashboard stats caching service with TIMING INSTRUMENTATION.
Handles cache layer for fast login redirect.
Cache TTL: 5 minutes (configurable).
"""
from django.core.cache import cache
from django.conf import settings
import logging
import time
from .selectors import get_all_dashboard_stats

logger = logging.getLogger(__name__)


# Cache configuration - Extended TTL for better performance
# Safe to extend because invalidate_dashboard_cache() is called on data changes
DASHBOARD_STATS_CACHE_TTL = getattr(settings, 'DASHBOARD_STATS_CACHE_TTL', 900)  # 15 min (was 5 min)


def get_cached_dashboard_stats(user_id):
    """
    Fetch dashboard stats from cache, or calculate fresh if expired.
    
    Args:
        user_id: Current user ID (for potential user-specific future caching)
        
    Returns:
        List of stat dicts for all modules
    """
    # Use global cache key (stats are same for all users)
    cache_key = 'dashboard_stats_global'
    
    # Try cache first
    t1 = time.time()
    stats = cache.get(cache_key)
    t2 = time.time()
    cache_lookup_ms = (t2 - t1) * 1000
    
    if stats is not None:
        logger.warning(f'CACHE_HIT: dashboard_stats (lookup={cache_lookup_ms:.2f}ms)')
        return stats
    
    # Cache miss: fetch fresh data
    logger.warning(f'CACHE_MISS: dashboard_stats (lookup={cache_lookup_ms:.2f}ms), calculating fresh...')
    
    try:
        t3 = time.time()
        stats = get_all_dashboard_stats()
        t4 = time.time()
        query_ms = (t4 - t3) * 1000
        
        logger.warning(f'QUERIES_EXECUTED: {query_ms:.2f}ms')
        
        # Cache for next 5 min (or configured TTL)
        cache.set(cache_key, stats, timeout=DASHBOARD_STATS_CACHE_TTL)
        logger.warning(f'STATS_CACHED: TTL={DASHBOARD_STATS_CACHE_TTL}s')
        
        return stats
    except Exception as e:
        logger.exception(f'Error calculating dashboard stats: {e}')
        # Return empty list on error instead of failing
        return []


def invalidate_dashboard_cache():
    """
    Manually invalidate dashboard cache.
    Call this after data-modifying operations (accept/reject/submit).
    Also increments cache version to invalidate HTML page cache.
    """
    cache_key = 'dashboard_stats_global'
    cache.delete(cache_key)
    
    # Increment version to invalidate all HTML caches
    version_key = 'dashboard_cache_version'
    current_version = cache.get(version_key, 0)
    cache.set(version_key, current_version + 1, timeout=None)  # No expiry
    
    logger.warning(f'CACHE_INVALIDATED: dashboard_stats + HTML cache (v{current_version + 1})')


def invalidate_user_modules_cache(user_id=None):
    """
    Invalidate user module permissions cache.
    Call this when user permissions are modified.
    
    Args:
        user_id: Specific user ID to invalidate. If None, invalidates all users.
    """
    if user_id:
        cache_key = f'user_modules_{user_id}'
        cache.delete(cache_key)
        logger.warning(f'USER_CACHE_INVALIDATED: user_id={user_id}')
    else:
        # Invalidate all user module caches (expensive, use sparingly)
        # In production, consider using cache prefix or versioning instead
        logger.warning('USER_CACHE_INVALIDATED: all users (pattern-based flush not implemented)')
        # Note: Django cache doesn't support pattern-based deletion natively
        # Consider using cache.clear() only if absolutely necessary


def refresh_dashboard_cache():
    """
    Proactively refresh dashboard cache.
    Can be called by background tasks or scheduled jobs.
    """
    invalidate_dashboard_cache()
    t1 = time.time()
    stats = get_all_dashboard_stats()
    t2 = time.time()
    query_ms = (t2 - t1) * 1000
    
    cache_key = 'dashboard_stats_global'
    cache.set(cache_key, stats, timeout=DASHBOARD_STATS_CACHE_TTL)
    logger.warning(f'CACHE_REFRESHED: {query_ms:.2f}ms for {len(stats)} modules')


# ═══════════════════════════════════════════════════════════════════════════════
# USAGE NOTES FOR OTHER MODULES
# ═══════════════════════════════════════════════════════════════════════════════
# 
# When to call invalidate_dashboard_cache():
# - After submitting lots (Input Screening, IQF, Brass QC, etc.)
# - After accepting/rejecting lots
# - After moving lots between stages
# - After any operation that changes dashboard counts
#
# Example:
#   from adminportal.services import invalidate_dashboard_cache
#   
#   def submit_lot(request):
#       # ... process submission ...
#       invalidate_dashboard_cache()  # Clear cache after data change
#       return Response({'status': 'success'})
#
# ═══════════════════════════════════════════════════════════════════════════════
