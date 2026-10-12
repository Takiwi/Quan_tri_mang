"""Views cho dashboard giám sát Wi-Fi."""

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404

from .models import Client, Event, ScanHistory


# ------------------------------------------------------------------ #
#  Template Views                                                     #
# ------------------------------------------------------------------ #

def dashboard_view(request):
    """Trang dashboard chính - tổng quan."""
    clients = Client.objects.all()
    total = clients.count()
    connected = clients.filter(state='connected').count()
    stale = clients.filter(state='stale').count()
    disconnected = clients.filter(state='disconnected').count()

    last_scan_obj = ScanHistory.objects.order_by('-id').first()
    last_scan = last_scan_obj.timestamp if last_scan_obj else 'Chưa quét'

    recent_events = Event.objects.order_by('-id')[:10]

    context = {
        'total': total,
        'connected': connected,
        'stale': stale,
        'disconnected': disconnected,
        'last_scan': last_scan,
        'recent_events': recent_events,
    }
    return render(request, 'monitor/dashboard.html', context)


def clients_view(request):
    """Trang danh sách tất cả client."""
    query = request.GET.get('q', '').strip()
    state_filter = request.GET.get('state', '').strip()

    clients = Client.objects.all()

    if query:
        clients = clients.filter(
            models_Q_search(query)
        )

    if state_filter:
        clients = clients.filter(state=state_filter)

    clients = clients.order_by('-last_seen')

    context = {
        'clients': clients,
        'query': query,
        'state_filter': state_filter,
    }
    return render(request, 'monitor/clients.html', context)


def client_detail_view(request, mac):
    """Trang chi tiết một client."""
    client = get_object_or_404(Client, mac=mac)
    events = Event.objects.filter(mac=mac).order_by('-id')[:20]

    context = {
        'client': client,
        'events': events,
    }
    return render(request, 'monitor/client_detail.html', context)


def events_view(request):
    """Trang lịch sử sự kiện."""
    event_type = request.GET.get('type', '').strip()
    severity = request.GET.get('severity', '').strip()

    events = Event.objects.all().order_by('-id')

    if event_type:
        events = events.filter(event_type=event_type)
    if severity:
        events = events.filter(severity=severity)

    paginator = Paginator(events, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'event_type': event_type,
        'severity': severity,
    }
    return render(request, 'monitor/events.html', context)


# ------------------------------------------------------------------ #
#  JSON API Endpoints                                                 #
# ------------------------------------------------------------------ #

def api_clients(request):
    """API: Danh sách client dưới dạng JSON."""
    clients = Client.objects.all().order_by('-last_seen')
    data = list(clients.values(
        'mac', 'ip', 'hostname', 'ssid', 'namespace',
        'first_seen', 'last_seen', 'state'
    ))
    return JsonResponse({'clients': data})


def api_events(request):
    """API: Sự kiện gần nhất dưới dạng JSON."""
    limit = int(request.GET.get('limit', 50))
    events = Event.objects.order_by('-id')[:limit]
    data = list(events.values(
        'id', 'timestamp', 'event_type', 'mac', 'message', 'severity'
    ))
    return JsonResponse({'events': data})


def api_stats(request):
    """API: Thống kê tổng hợp."""
    clients = Client.objects.all()
    total = clients.count()
    connected = clients.filter(state='connected').count()
    disconnected = clients.filter(state='disconnected').count()
    stale = clients.filter(state='stale').count()

    last_scan_obj = ScanHistory.objects.order_by('-id').first()
    last_scan = last_scan_obj.timestamp if last_scan_obj else ''

    return JsonResponse({
        'total_clients': total,
        'connected_clients': connected,
        'disconnected_clients': disconnected,
        'stale_clients': stale,
        'last_scan': last_scan,
    })


def api_scan_history(request):
    """API: Lịch sử quét (cho biểu đồ)."""
    limit = int(request.GET.get('limit', 100))
    history = ScanHistory.objects.order_by('-id')[:limit]
    data = list(history.values(
        'id', 'timestamp', 'total_clients', 'connected_clients'
    ))
    # Đảo ngược để thứ tự thời gian tăng dần (cho biểu đồ)
    data.reverse()
    return JsonResponse({'scan_history': data})


# ------------------------------------------------------------------ #
#  Helper                                                             #
# ------------------------------------------------------------------ #

def models_Q_search(query):
    """Tạo Q object để tìm kiếm client theo MAC, IP, hostname."""
    from django.db.models import Q
    return (
        Q(mac__icontains=query) |
        Q(ip__icontains=query) |
        Q(hostname__icontains=query)
    )

