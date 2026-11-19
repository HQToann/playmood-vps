import logging
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache

logger = logging.getLogger(__name__)

def health_check(request):
    """
    Endpoint kiểm tra trạng thái sức khoẻ dịch vụ
    - ?type=liveness: Chỉ kiểm tra tiến web còn sống (không đụng DB/Redis)
    - Mặc định hoặc ?type=readiness: Kiểm tra sâu cả DB và Redis trên VM3
    """
    probe_type = request.GET.get('type', 'readiness')

    # 1. Nếu là livenessProbe: Chỉ cần Django phản hồi được là Ok
    if probe_type == 'liveness':
        return JsonResponse(
            {
                'status': 'alive'
            },
            status = 200
        )

    # 2. Nếu là readinessProbe: Kiểm tra toàn diện DB và Redis
    checks = {}
    is_healthy = True

    # Kiểm tra DB (PostgreSQL)
    try:
        connection.ensure_connection()
        checks['database'] = 'ok'
    except Exception as e:
        logger.error("Health check - Lỗi kết nối Database: %s", str(e))
        checks['database'] = 'error' # Không show chi tiết IP/Port ra ngoài
        is_healthy = False

    # Kiểm tra Redis Cache
    try:
        cache.set('k3s_health', '1', timeout=5)
        val = cache.get('k3s_health')
        if val == '1':
            checks['cache'] = 'oke'
        else:
            checks['cache'] = 'miss'
            # Cân nhắc: Nếu Redis là bắt buộc, bắt dòng dưới:
            # is_healthy = False
    except Exception as e:
        logger.error("Health check - Lỗi kết nối Redis: %s", str(e))
        checks['cache'] = 'error'
        is_healthy = False

    status_code = 200 if is_healthy else 503
    return JsonResponse(
        {
            'status': 'healthy' if is_healthy else 'unhealthy',
            'checks': checks,
        },
        status=status_code
    )