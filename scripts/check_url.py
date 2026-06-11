import sys, os
sys.path.insert(0, r'd:\Workspace\Watchcase\TTT-Jan2026')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')
import django
django.setup()

from django.urls import resolve
r = resolve('/adminportal/api/users/1/')
view_func = r.func
print('View func:', view_func)
print('View cls:', getattr(view_func, 'cls', 'N/A'))
print('permission_classes:', getattr(getattr(view_func, 'cls', None), 'permission_classes', 'N/A'))
print('http_method_names:', getattr(getattr(view_func, 'cls', None), 'http_method_names', 'N/A'))

# Check decorators / wrapper chain
f = view_func
chain = []
while hasattr(f, '__wrapped__'):
    chain.append(f.__qualname__)
    f = f.__wrapped__
chain.append(getattr(f, '__qualname__', str(f)))
print('Wrapper chain:', chain)
