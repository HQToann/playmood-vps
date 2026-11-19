import logging
from django.http import JsonResponse
from accounts.exceptions import AppException

logger = logging.getLogger(__name__)

class GlobalErrorMiddleware:
    """Bắt các ngoại lệ ở tầng View và trả về JSON đồng nhất cho API."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        # Chỉ xử lý các route API
        if not request.path.startswith('/api/'):
            return None

        # 1. Trường hợp: Lỗi nghiệp vụ có kiểm soát (AppException)
        if isinstance(exception, AppException):
            status_map = {
                'VALIDATION_ERROR': 400,
                'AUTH_REQUIRED': 401,
                'PERMISSION_DENIED': 403,
                'ACCOUNT_INACTIVE': 403,
                'BLOCKED': 403,
                'ARTIST_ONLY': 403,
                'ADMIN_ONLY': 403,
                'NOT_FOUND': 404,
                'ALREADY_EXISTS': 409,
            }
            error_code = getattr(exception, 'error_code', 'API_ERROR')
            # Ưu tiên status_code gắn trực tiếp trong exception (nếu có), sau đó mới tra status_map
            status_code = getattr(exception, 'status_code', status_map.get(error_code, 400))

            payload = {
                'code': error_code,
                'message': getattr(exception, 'message', str(exception)),
            }
            if hasattr(exception, 'fields') and exception.fields:
                payload['fields'] = exception.fields

            # Ghi log cảnh báo mức WARNING
            logger.warning("API AppException [%s] tại %s: %s", error_code, request.path, payload['message'])

            return JsonResponse({'success': False, 'error': payload}, status=status_code)

        # 2. Trường hợp: Lỗi server không lường trước (Unhandled 500)
        # Ghi log kèm toàn bộ stack trace để debug
        logger.exception("Lỗi hệ thống chưa xử lý tại %s: %s", request.path, str(exception))
        return JsonResponse(
            {
                'success': False,
                'error': {
                    'code': 'INTERNAL_SERVER_ERROR',
                    'message': 'Đã xảy ra lỗi máy chủ nội bộ. Vui lòng thử lại sau.'
                }
            },
            status=500
        )