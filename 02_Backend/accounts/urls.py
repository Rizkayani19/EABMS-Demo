from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('switch-account/<int:account_id>/', views.switch_account, name='switch_account'),
    path('switch-fy/<int:fy_id>/', views.switch_fy, name='switch_fy'),
    path('audit-log/', views.audit_log_view, name='audit_log'),
    path('help/', views.help_manual, name='help'),
    path('users/', views.user_list, name='user_list'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_update, name='user_update'),
    path('users/<int:user_id>/password/', views.user_password_reset, name='user_password_reset'),
    path('users/<int:user_id>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    path('users/<int:user_id>/delete/', views.user_delete, name='user_delete'),
    path('users/bulk-delete/', views.user_bulk_delete, name='user_bulk_delete'),
]
