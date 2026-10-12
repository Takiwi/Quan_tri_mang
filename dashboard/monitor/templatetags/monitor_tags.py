"""Custom template tags cho dashboard giám sát Wi-Fi."""

from datetime import datetime, timezone

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def state_badge(state):
    """Trả về badge Bootstrap theo trạng thái client."""
    badges = {
        "connected": '<span class="badge bg-success">Kết nối</span>',
        "stale": '<span class="badge bg-warning text-dark">Không ổn định</span>',
        "disconnected": '<span class="badge bg-danger">Mất kết nối</span>',
    }
    return mark_safe(
        badges.get(state, f'<span class="badge bg-secondary">{state}</span>')
    )


@register.filter
def severity_badge(severity):
    """Trả về badge Bootstrap theo mức độ nghiêm trọng."""
    badges = {
        "info": '<span class="badge bg-info text-dark">Thông tin</span>',
        "warning": '<span class="badge bg-warning text-dark">Cảnh báo</span>',
        "critical": '<span class="badge bg-danger">Nghiêm trọng</span>',
    }
    return mark_safe(
        badges.get(severity, f'<span class="badge bg-secondary">{severity}</span>')
    )


@register.filter
def event_type_label(event_type):
    """Trả về nhãn tiếng Việt cho loại sự kiện."""
    labels = {
        "client_connected": "🟢 Kết nối mới",
        "client_disconnected": "🔴 Mất kết nối",
        "client_returned": "🔵 Quay lại",
        "threshold_exceeded": "⚠️ Vượt ngưỡng",
    }
    return labels.get(event_type, event_type)


@register.filter
def time_ago(iso_str):
    """Chuyển chuỗi ISO datetime thành thời gian tương đối (VD: '5 phút trước')."""
    if not iso_str:
        return "N/A"

    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - dt

        seconds = int(diff.total_seconds())
        if seconds < 0:
            return "vừa xong"
        if seconds < 60:
            return f"{seconds} giây trước"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} phút trước"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} giờ trước"
        days = hours // 24
        return f"{days} ngày trước"
    except (ValueError, TypeError):
        return iso_str
