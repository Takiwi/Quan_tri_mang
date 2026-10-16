"""
Django models cho giám sát Wi-Fi.
Các model này là UNMANAGED (managed=False) vì bảng được tạo bởi wifimon/storage.py.
"""

from django.db import models


class Client(models.Model):
    """Thông tin client Wi-Fi."""

    mac = models.CharField(max_length=17, primary_key=True)
    ip = models.CharField(max_length=45, blank=True, default="")
    hostname = models.CharField(max_length=255, blank=True, default="")
    ssid = models.CharField(max_length=255, blank=True, default="")
    namespace = models.CharField(max_length=255, blank=True, default="")
    connected_since = models.CharField(max_length=30, blank=True, default="")
    first_seen = models.CharField(max_length=30, blank=True, default="")
    last_seen = models.CharField(max_length=30, blank=True, default="")
    state = models.CharField(max_length=20, default="connected")
    source = models.CharField(max_length=32, blank=True, default="")
    missed_scans = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "clients"

    def __str__(self):
        return f"{self.mac} ({self.hostname or self.ip})"


class Event(models.Model):
    """Sự kiện / cảnh báo giám sát."""

    timestamp = models.CharField(max_length=30)
    event_type = models.CharField(max_length=50)
    mac = models.CharField(max_length=17, blank=True, default="")
    message = models.TextField(blank=True, default="")
    severity = models.CharField(max_length=20, default="info")

    class Meta:
        managed = False
        db_table = "events"
        ordering = ["-id"]

    def __str__(self):
        return f"[{self.severity}] {self.event_type}: {self.message[:50]}"


class ScanHistory(models.Model):
    """Lịch sử mỗi lần quét."""

    timestamp = models.CharField(max_length=30)
    total_clients = models.IntegerField(default=0)
    connected_clients = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "scan_history"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.timestamp}: {self.connected_clients}/{self.total_clients}"
