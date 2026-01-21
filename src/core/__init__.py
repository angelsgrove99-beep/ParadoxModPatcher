"""Core module for Paradox Mod Patcher"""

try:
    from .parser import ParadoxParser, ParadoxSerializer, parse_file, serialize_to_file
    from .merger import SmartMerger, MergeResult, MergeStrategy, MultiModMerger
    from .scanner import ModScanner, ModInfo, FileConflict, ScanResult, get_paradox_mods_path
    from .patch_generator import PatchGenerator, PatchResult
    from .smart_merger import (
        StructurePreservingMerger, 
        FileMergeResult, 
        read_mod_name, 
        read_mod_dependencies,
        validate_mod_compatibility
    )
    from .smart_patch_generator import SmartPatchGenerator, PatchStats, PatchProgress
except ImportError:
    from parser import ParadoxParser, ParadoxSerializer, parse_file, serialize_to_file
    from merger import SmartMerger, MergeResult, MergeStrategy, MultiModMerger
    from scanner import ModScanner, ModInfo, FileConflict, ScanResult, get_paradox_mods_path
    from patch_generator import PatchGenerator, PatchResult
    from smart_merger import (
        StructurePreservingMerger, 
        FileMergeResult, 
        read_mod_name, 
        read_mod_dependencies,
        validate_mod_compatibility
    )
    from smart_patch_generator import SmartPatchGenerator, PatchStats, PatchProgress

__all__ = [
    'ParadoxParser',
    'ParadoxSerializer', 
    'parse_file',
    'serialize_to_file',
    'SmartMerger',
    'MergeResult',
    'MergeStrategy',
    'MultiModMerger',
    'ModScanner',
    'ModInfo',
    'FileConflict',
    'ScanResult',
    'get_paradox_mods_path',
    'PatchGenerator',
    'PatchResult',
    'StructurePreservingMerger',
    'FileMergeResult',
    'read_mod_name',
    'read_mod_dependencies',
    'validate_mod_compatibility',
    'SmartPatchGenerator',
    'PatchStats',
    'PatchProgress'
]
