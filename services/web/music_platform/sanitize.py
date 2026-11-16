"""
music_platform/sanitize.py

Cung cấp các hàm làm sạch dữ liệu đầu vào (Input Sanitization) cho toàn bộ hệ thống.
Re-export từ utils.sanitizer để đảm bảo tính tập trung và thống nhất.
"""

from utils.sanitizer import sanitize_text, sanitize_url

__all__ = ['sanitize_text', 'sanitize_url']

