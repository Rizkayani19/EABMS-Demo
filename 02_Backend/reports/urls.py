from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_center, name='report_center'),
    path('management-workbook/', views.management_workbook, name='management_workbook'),
    path('budget-word-document/', views.budget_word_document, name='budget_word_document'),
    path('<slug:slug>/', views.view_report, name='view_report'),
]
