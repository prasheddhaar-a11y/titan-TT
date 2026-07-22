import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','watchcase_tracker.settings')
import django
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model

client = Client(raise_request_exception=True)
User = get_user_model()
user = User.objects.filter(is_superuser=True, is_active=True).order_by('id').first()
print('SUPERUSER', getattr(user,'username',None))
if user:
    client.force_login(user)

resp = client.get('/admin/modelmasterapp/modelversioncomparisonimage/', HTTP_HOST='127.0.0.1')
print('STATUS', resp.status_code)
