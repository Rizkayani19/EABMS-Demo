from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('masters/', include('masters.urls', namespace='masters')),
    path('reports/', include('reports.urls', namespace='reports')),
    path('', include('core.urls', namespace='core')),
]
