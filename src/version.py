"""
Paradox Mod Patcher version information
"""

__version__ = "2.0.0"
__author__ = "Paradox Mod Patcher Contributors"
__app_name__ = "Paradox Mod Patcher"

VERSION_INFO = {
    "major": 2,
    "minor": 0,
    "patch": 0,
    "release": "stable"
}

def get_version_string() -> str:
    """Returns formatted version string"""
    return f"{__app_name__} v{__version__}"
