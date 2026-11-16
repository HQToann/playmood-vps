import time
import logging

# Ghi log thông tin liên quan request HTTP
logger = logging.getLogger('django.request')

class RequestLoggingMiddleware:
    """
    Ghi log thời gian xử lý các request API.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time() # thời gian thực
        response = self.get_response(request)
        # ghi log các endpoint bắt đầu bằng /api/
        if request.path.startswith('/api/'):
            duration_ms = (time.time() - start_time) * 1000 # tính toán thời gian thực thi
            logger.info(
                "%s %s -> %s (%.1fms)", # [Phương thức] [Đường dẫn] -> [Mã HTTP status] ([Thời gian xử lý]ms)
                request.method,
                request.path,
                response.status_code,
                duration_ms
            )
        return response
