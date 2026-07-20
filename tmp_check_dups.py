import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')
django.setup()

from modelmasterapp.models import ModelMaster
from django.db.models import Count

dups = ModelMaster.objects.values('plating_stk_no').annotate(c=Count('id')).filter(c__gt=1)
print('Duplicate plating_stk_no count:', dups.count())
print(list(dups)[:10])

# Also check all 2648 model master records
print('\nAll 2648 ModelMaster records:')
for mm in ModelMaster.objects.filter(plating_stk_no__startswith='2648'):
    print(mm.id, mm.model_no, mm.plating_stk_no)
