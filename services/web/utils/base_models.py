import uuid
from django.db import models

# Các trường thông tin chung mà hầu hết các bảng csdl đều cần
class TimeStampedModel(models.Model):
    """Abstract base model cung cấp uuid primary và timestamps."""
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Ngày tạo'
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Cập nhật lần cuối'
    )

    # Model trừ tượng django
    class Meta:
        abstract = True
