from django.urls import path
from django.shortcuts import redirect
from modelmasterapp.views import *


def legacy_login_redirect(request):
    return redirect('login')

urlpatterns = [
    path('', legacy_login_redirect, name='legacy-login-api'),
    path('base/', BaseAPIView.as_view(), name='base-api'),
    path('api/get-lot-by-model/', GetLotByModelAPIView.as_view(), name='get-lot-by-model'),
    path('logout/', logout_view, name='logout'),
    path('delete_all/', delete_all_tables, name='delete_all_tables'),
    path('get-plating-images/', get_plating_images, name='get_plating_images'),

]
