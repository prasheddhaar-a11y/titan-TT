"""
Dashboard stats caching service with TIMING INSTRUMENTATION.
Handles cache layer for fast login redirect.
Cache TTL: 5 minutes (configurable).
"""
from django.core.cache import cache
from django.conf import settings
from django.db import transaction
from django.contrib.auth.models import Group
from django.utils.text import slugify
import logging
import time
from .selectors import get_dashboard_stat_labels, get_dashboard_stats_for_labels
from .models import Module, ShortcutConfiguration, UserModuleProvision
from .module_registry import LEGACY_MODULE_NAME_MAP, MODULE_REGISTRY, USER_CATEGORY_MODULES

logger = logging.getLogger(__name__)

USER_MODULE_CACHE_TTL = 300
MODULE_REGISTRY_CACHE_KEY = 'adminportal_module_registry_seeded_v2'
MODULE_REGISTRY_NAMES = [entry['name'] for entry in MODULE_REGISTRY]

DASHBOARD_MODULE_ACCESS = {
    'Day Planning': {'Data Upload', 'DP Pick Table', 'DP Complete Table'},
    'Input Screening': {
        'Input Screening',
        'Input Pick Table', 'Input Completed Table', 'Input Accept Table',
        'Input Reject Table', 'Input Main Table', 'Input Complete Table',
    },
    'Brass QC': {'Brass Qc Pick Table', 'Brass Qc Completed Table', 'Brass QC Pick Table', 'Brass QC Complete Table', 'Brass QC Completed Table'},
    'Brass Audit': {'Brass Audit Pick Table', 'Brass Audit Complete Table', 'Brass Audit Reject Table'},
    'IQF': {'IQF Pick Table', 'IQF Completed Table', 'IQF Accept Table', 'IQF Reject Table'},
    'Jig Loading': {'Jig Pick Table', 'Jig Completed Table'},
    'Jig Unloading': {'JUL Main Table', 'JUL Completed', 'JUL Main Table Zone 2', 'JUL Completed Zone 2'},
    'Inprocess Inspection': {'IP Main', 'IP Completed'},
    'Nickel Inspection': {'Nickel Main Table', 'Nickel Completed Table'},
    'Nickel Audit': {'NA Pick Table', 'NA Completed'},
    'Spider Spindle': {
        'Spider Spindle', 'Spider Spindle Z1', 'Spider Spindle Z2',
        'Spider Spindle Z1 Pick Table', 'Spider Spindle Z1 Completed Table',
        'Spider Spindle Z2 Pick Table', 'Spider Spindle Z2 Completed Table',
    },
}


def ensure_module_registry_seeded():
    """Create/update canonical modules, headings, file paths, and user categories."""
    if cache.get(MODULE_REGISTRY_CACHE_KEY):
        return

    with transaction.atomic():
        module_by_name = {}
        for entry in MODULE_REGISTRY:
            module, _ = Module.objects.update_or_create(
                name=entry['name'],
                defaults={
                    'menu_title': entry.get('menu_title') or entry['name'],
                    'headings': entry.get('headings') or [],
                    'html_file': entry.get('file_name') or '',
                },
            )
            module_by_name[module.name] = module

        for group_name, module_names in USER_CATEGORY_MODULES.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            modules = [module_by_name[name] for name in module_names if name in module_by_name]
            group.modules.set(modules)

    cache.set(MODULE_REGISTRY_CACHE_KEY, True, timeout=USER_MODULE_CACHE_TTL)


def is_admin_user(user):
    """Return True for superusers, Admin group users, or Admin department users."""
    if not getattr(user, 'is_authenticated', False):
        return False

    return (
        user.is_superuser
        or user.groups.filter(name__iexact='Admin').exists()
        or (
            hasattr(user, 'userprofile')
            and user.userprofile.department
            and user.userprofile.department.name.lower() == 'admin'
        )
    )


def _group_module_queryset(user):
    """Modules mapped directly to the user's selected user-category groups."""
    ensure_module_registry_seeded()
    return Module.objects.filter(groups__in=user.groups.all()).distinct()


def _all_module_names():
    ensure_module_registry_seeded()
    existing_names = set(Module.objects.filter(name__in=MODULE_REGISTRY_NAMES).values_list('name', flat=True))
    return [name for name in MODULE_REGISTRY_NAMES if name in existing_names]


def _registry_modules():
    modules_by_name = {module.name: module for module in Module.objects.filter(name__in=MODULE_REGISTRY_NAMES)}
    return [modules_by_name[name] for name in MODULE_REGISTRY_NAMES if name in modules_by_name]


def _expand_legacy_module_names(module_names):
    expanded = []
    for name in module_names:
        replacements = LEGACY_MODULE_NAME_MAP.get(name, [name])
        for replacement in replacements:
            if replacement not in expanded:
                expanded.append(replacement)
    return expanded


def get_dashboard_labels_for_modules(allowed_module_names):
    """Resolve visible dashboard labels from canonical sidebar/module permissions."""
    allowed_set = set(_expand_legacy_module_names(allowed_module_names or []))
    if not allowed_set:
        return []

    return [
        label
        for label in get_dashboard_stat_labels()
        if allowed_set.intersection(DASHBOARD_MODULE_ACCESS.get(label, {label}))
    ]


def get_user_allowed_module_names(user):
    """
    Resolve dashboard/sidebar module access for a user.

    Priority:
    1. Admin users get all modules.
    2. User Category groups with mapped Module rows restrict access to those modules.
    3. Manual UserModuleProvision rows are used for normal/custom users.
    4. Legacy fallback keeps existing unrestricted users working until provisioned.
    """
    if not getattr(user, 'is_authenticated', False):
        return []

    ensure_module_registry_seeded()

    cache_key = f'user_modules_{user.id}'
    cached_modules = cache.get(cache_key)
    if cached_modules is not None:
        return cached_modules

    try:
        if is_admin_user(user):
            modules = _all_module_names()
        else:
            group_modules = list(_group_module_queryset(user).values_list('name', flat=True))
            if group_modules:
                modules = group_modules
            else:
                provisioned_modules = list(
                    UserModuleProvision.objects.filter(user=user)
                    .values_list('module_name', flat=True)
                    .distinct()
                )
                modules = _expand_legacy_module_names(provisioned_modules) if provisioned_modules else []

        cache.set(cache_key, modules, timeout=USER_MODULE_CACHE_TTL)
        return modules
    except Exception:
        logger.exception('Error resolving user module access for user_id=%s', getattr(user, 'id', None))
        return list(
            UserModuleProvision.objects.filter(user=user)
            .values_list('module_name', flat=True)
            .distinct()
        )


def get_user_allowed_module_payload(user):
    """Return editable module payloads for the admin provisioning UI."""
    if not getattr(user, 'is_authenticated', False):
        return []

    ensure_module_registry_seeded()

    def module_payload(module, selected_headings=None):
        all_headings = module.headings or []
        return {
            'name': module.name,
            'headings': selected_headings if selected_headings is not None else all_headings,
            'all_headings': all_headings,
            'file_name': module.html_file or '',
        }

    if is_admin_user(user):
        modules = _registry_modules()
        return [module_payload(module) for module in modules]

    group_modules = list(_group_module_queryset(user))
    if group_modules:
        return [module_payload(module) for module in group_modules]

    provisions = list(UserModuleProvision.objects.filter(user=user))
    if provisions:
        modules_by_name = {module.name: module for module in Module.objects.filter(name__in=MODULE_REGISTRY_NAMES)}
        payload = []
        seen_names = set()
        for provision in provisions:
            replacement_names = LEGACY_MODULE_NAME_MAP.get(provision.module_name, [provision.module_name])
            for module_name in replacement_names:
                if module_name in seen_names:
                    continue
                seen_names.add(module_name)
                module = modules_by_name.get(module_name)
                if module:
                    selected_headings = provision.headings or module.headings or []
                    payload.append(module_payload(module, selected_headings))
                    continue
                payload.append({
                    'name': module_name,
                    'headings': provision.headings or [],
                    'all_headings': provision.headings or [],
                    'file_name': provision.file_name or '',
                })
        return payload

    return []


def get_active_shortcut_configurations():
    """Return active shortcut configuration used by the global keyboard manager."""
    shortcuts = ShortcutConfiguration.objects.filter(is_active=True).order_by('sort_order', 'label', 'code')
    return [
        {
            'code': shortcut.code,
            'keys': shortcut.keys or [],
            'key_display': shortcut.key_display,
            'label': shortcut.label,
            'description': shortcut.description or '',
            'action_type': shortcut.action_type,
            'target_selector': shortcut.target_selector or '',
            'fallback_selector': shortcut.fallback_selector or '',
            'contexts': shortcut.contexts or [],
            'allow_in_modal': shortcut.allow_in_modal,
            'allow_when_typing': shortcut.allow_when_typing,
            'sort_order': shortcut.sort_order,
        }
        for shortcut in shortcuts
    ]


def sync_user_module_provisions_from_group(user):
    """Persist group-mapped modules as UserModuleProvision rows for fixed user categories."""
    if not getattr(user, 'is_authenticated', False):
        return False

    ensure_module_registry_seeded()

    group_modules = list(_group_module_queryset(user))
    if not group_modules:
        return False

    with transaction.atomic():
        UserModuleProvision.objects.filter(user=user).delete()
        for module in group_modules:
            UserModuleProvision.objects.update_or_create(
                user=user,
                module_name=module.name,
                defaults={
                    'headings': module.headings or [],
                    'file_name': module.html_file or '',
                },
            )

    invalidate_user_modules_cache(user.id)
    return True


def filter_dashboard_stats_for_modules(dashboard_stats, allowed_module_names):
    """Keep only dashboard cards backed by the user's allowed module names."""
    visible_labels = set(get_dashboard_labels_for_modules(allowed_module_names))
    return [stat for stat in dashboard_stats if stat.get('label') in visible_labels]


# Cache configuration - Extended TTL for better performance
# Safe to extend because invalidate_dashboard_cache() is called on data changes
DASHBOARD_STATS_CACHE_TTL = getattr(settings, 'DASHBOARD_STATS_CACHE_TTL', 900)  # 15 min (was 5 min)


def _dashboard_cache_key(label):
    return f"dashboard_stats_{slugify(label).replace('-', '_')}"


def get_cached_dashboard_stats(user_id=None, allowed_module_names=None):
    """
    Fetch dashboard stats from cache, calculating only visible cards on miss.
    """
    labels = (
        get_dashboard_labels_for_modules(allowed_module_names)
        if allowed_module_names is not None
        else get_dashboard_stat_labels()
    )
    if not labels:
        return []

    cache_keys = {label: _dashboard_cache_key(label) for label in labels}

    t1 = time.time()
    cached_by_key = cache.get_many(cache_keys.values())
    t2 = time.time()
    cache_lookup_ms = (t2 - t1) * 1000

    stats_by_label = {
        label: cached_by_key[cache_key]
        for label, cache_key in cache_keys.items()
        if cache_key in cached_by_key
    }
    missing_labels = [label for label in labels if label not in stats_by_label]

    if not missing_labels:
        logger.warning(f'CACHE_HIT: dashboard_stats labels={labels} (lookup={cache_lookup_ms:.2f}ms)')
        return [stats_by_label[label] for label in labels]

    logger.warning(
        f'CACHE_MISS: dashboard_stats missing={missing_labels} '
        f'(lookup={cache_lookup_ms:.2f}ms), calculating fresh...'
    )

    try:
        t3 = time.time()
        fresh_stats = get_dashboard_stats_for_labels(missing_labels)
        t4 = time.time()
        query_ms = (t4 - t3) * 1000

        logger.warning(f'QUERIES_EXECUTED: {query_ms:.2f}ms')

        cache_payload = {}
        for stat in fresh_stats:
            label = stat.get('label')
            if not label:
                continue
            stats_by_label[label] = stat
            cache_payload[_dashboard_cache_key(label)] = stat

        if cache_payload:
            cache.set_many(cache_payload, timeout=DASHBOARD_STATS_CACHE_TTL)
            logger.warning(f'STATS_CACHED: labels={list(cache_payload.keys())} TTL={DASHBOARD_STATS_CACHE_TTL}s')

        return [stats_by_label[label] for label in labels if label in stats_by_label]
    except Exception as e:
        logger.exception(f'Error calculating dashboard stats: {e}')
        # Return empty list on error instead of failing
        return [stats_by_label[label] for label in labels if label in stats_by_label]


def invalidate_dashboard_cache():
    """
    Manually invalidate dashboard cache.
    Call this after data-modifying operations (accept/reject/submit).
    Also increments cache version to invalidate HTML page cache.
    """
    cache_key = 'dashboard_stats_global'
    cache.delete(cache_key)
    cache.delete_many([_dashboard_cache_key(label) for label in get_dashboard_stat_labels()])
    
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
    stats = get_dashboard_stats_for_labels()
    t2 = time.time()
    query_ms = (t2 - t1) * 1000

    cache.set_many(
        {_dashboard_cache_key(stat['label']): stat for stat in stats if stat.get('label')},
        timeout=DASHBOARD_STATS_CACHE_TTL,
    )
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
