"""Utility functions"""


def safe_filename(name: str) -> str:
    """Преобразует строку в безопасное имя файла"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name


def format_size(size_bytes: int) -> str:
    """Форматирует размер в человекочитаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
