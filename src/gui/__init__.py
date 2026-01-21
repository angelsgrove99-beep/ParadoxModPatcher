"""GUI module for Paradox Mod Patcher"""

try:
    from .main_window import MainWindow
except ImportError:
    from main_window import MainWindow

__all__ = ['MainWindow']
