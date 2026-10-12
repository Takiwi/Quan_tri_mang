"""
Cấu hình URL cho dự án Dashboard.
Chuyển tiếp tất cả URL đến ứng dụng monitor.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('monitor.urls')),
]
