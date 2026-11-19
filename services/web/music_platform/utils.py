def optimize_cloudinary_url(url: str, resource_type: str = 'image') -> str:
    """
    Tối ưu hóa đường dẫn media lưu trên Cloudinary (tự động nén q_auto, f_auto).
    
    Args:
        url: Đường dẫn URL của file ảnh hoặc âm thanh.
        resource_type: Loại tài nguyên ('image' hoặc 'audio').
        
    Returns:
        URL đã được tối ưu hóa cho CDN Cloudinary hoặc URL gốc nếu là file local.
    """
    if not url:
        return url

    # Nếu không phải link Cloudinary (ví dụ file lưu ở local /media/ khi dev), trả về nguyên bản
    if 'res.cloudinary.com' not in url:
        return url

    # Chèn cờ f_auto,q_auto ngay sau /upload/ nếu chưa có
    if '/upload/' in url and '/upload/f_auto,q_auto/' not in url:
        return url.replace('/upload/', '/upload/f_auto,q_auto/', 1)

    return url