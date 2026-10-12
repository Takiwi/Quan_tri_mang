from django.contrib import admin
from .models import Client, Event, ScanHistory

# Không register vào admin vì models là unmanaged
# Nếu muốn xem trong admin, uncomment bên dưới:
# admin.site.register(Client)
# admin.site.register(Event)
# admin.site.register(ScanHistory)
