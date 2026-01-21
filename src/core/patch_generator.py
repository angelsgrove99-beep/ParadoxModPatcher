"""
Patch Generator
Генератор патчей совместимости
"""

import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

try:
    from .scanner import ModInfo, FileConflict, ScanResult
    from .merger import SmartMerger, MergeResult, MergeStrategy
except ImportError:
    from scanner import ModInfo, FileConflict, ScanResult
    from merger import SmartMerger, MergeResult, MergeStrategy


@dataclass
class PatchFile:
    """Информация о файле в патче"""
    relative_path: str
    source_type: str  # 'merged', 'copied', 'generated'
    source_mods: List[str] = field(default_factory=list)
    changes_count: int = 0
    has_conflicts: bool = False


@dataclass 
class PatchResult:
    """Результат генерации патча"""
    success: bool
    output_path: Path = None
    files: List[PatchFile] = field(default_factory=list)
    merged_count: int = 0
    copied_count: int = 0
    failed_count: int = 0
    errors: List[str] = field(default_factory=list)


class PatchGenerator:
    """Генератор патчей совместимости"""
    
    def __init__(self, output_path: Path, patch_name: str = "AutoPatch"):
        self.output_path = Path(output_path)
        self.patch_name = patch_name
        self.files: List[PatchFile] = []
        self.errors: List[str] = []
        
    def generate_from_conflicts(
        self,
        conflicts: List[FileConflict],
        strategy: MergeStrategy = MergeStrategy.SMART_MERGE,
        include_unique: bool = True
    ) -> PatchResult:
        """
        Генерирует патч на основе списка конфликтов
        
        Args:
            conflicts: Список конфликтов файлов
            strategy: Стратегия мержа
            include_unique: Включать ли уникальные файлы из приоритетных модов
        """
        result = PatchResult(success=True, output_path=self.output_path)
        
        # Создаём директорию
        if self.output_path.exists():
            shutil.rmtree(self.output_path)
        self.output_path.mkdir(parents=True)
        
        # Обрабатываем конфликты
        for conflict in conflicts:
            if len(conflict.mods) < 2:
                continue
                
            # Берём первый мод как базу, последний как приоритет
            base_mod = conflict.mods[0]
            priority_mod = conflict.mods[-1]
            
            base_file = base_mod.files.get(conflict.relative_path)
            priority_file = priority_mod.files.get(conflict.relative_path)
            
            if not base_file or not priority_file:
                continue
                
            # Мержим
            merger = SmartMerger(base_mod.name, priority_mod.name)
            merge_result = merger.merge_files(base_file, priority_file, strategy)
            
            if merge_result.success:
                # Сохраняем смерженный файл
                output_file = self.output_path / conflict.relative_path
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(merge_result.merged_content, encoding='utf-8-sig')
                
                patch_file = PatchFile(
                    relative_path=conflict.relative_path,
                    source_type='merged',
                    source_mods=[base_mod.name, priority_mod.name],
                    changes_count=len(merge_result.changes),
                    has_conflicts=len(merge_result.conflicts) > 0
                )
                result.files.append(patch_file)
                result.merged_count += 1
            else:
                result.errors.append(f"Failed to merge {conflict.relative_path}: {merge_result.error}")
                result.failed_count += 1
                
        # Генерируем descriptor.mod
        self._generate_descriptor()
        
        # Генерируем .mod файл
        self._generate_mod_file()
        
        # Генерируем README
        self._generate_readme(result)
        
        result.success = result.failed_count == 0
        return result
    
    def generate_full_patch(
        self,
        mods: List[ModInfo],
        strategy: MergeStrategy = MergeStrategy.SMART_MERGE
    ) -> PatchResult:
        """
        Генерирует полный патч из списка модов
        
        Первый мод - база, остальные применяются последовательно
        """
        result = PatchResult(success=True, output_path=self.output_path)
        
        if len(mods) < 2:
            result.success = False
            result.errors.append("Need at least 2 mods")
            return result
            
        # Создаём директорию
        if self.output_path.exists():
            shutil.rmtree(self.output_path)
        self.output_path.mkdir(parents=True)
        
        base_mod = mods[0]
        priority_mods = mods[1:]
        
        # Находим все уникальные файлы из всех модов
        all_files: Dict[str, List[Tuple[ModInfo, Path]]] = {}
        
        for mod in mods:
            for rel_path, file_path in mod.files.items():
                if rel_path not in all_files:
                    all_files[rel_path] = []
                all_files[rel_path].append((mod, file_path))
                
        # Обрабатываем каждый файл
        for rel_path, sources in all_files.items():
            if len(sources) == 1:
                # Уникальный файл - копируем
                mod, file_path = sources[0]
                output_file = self.output_path / rel_path
                output_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, output_file)
                
                result.files.append(PatchFile(
                    relative_path=rel_path,
                    source_type='copied',
                    source_mods=[mod.name]
                ))
                result.copied_count += 1
                
            else:
                # Конфликт - мержим последовательно
                current_content = None
                source_mods = []
                
                for mod, file_path in sources:
                    if current_content is None:
                        # Первый файл
                        with open(file_path, 'r', encoding='utf-8-sig') as f:
                            current_content = f.read()
                        source_mods.append(mod.name)
                    else:
                        # Мержим с текущим
                        with open(file_path, 'r', encoding='utf-8-sig') as f:
                            mod_content = f.read()
                            
                        merger = SmartMerger("Current", mod.name)
                        merge_result = merger.merge_contents(current_content, mod_content, strategy)
                        
                        if merge_result.success or merge_result.merged_content:
                            current_content = merge_result.merged_content
                            source_mods.append(mod.name)
                        else:
                            result.errors.append(f"Merge failed for {rel_path} with {mod.name}")
                            
                # Сохраняем результат
                if current_content:
                    output_file = self.output_path / rel_path
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    output_file.write_text(current_content, encoding='utf-8-sig')
                    
                    result.files.append(PatchFile(
                        relative_path=rel_path,
                        source_type='merged',
                        source_mods=source_mods,
                        changes_count=len(source_mods) - 1
                    ))
                    result.merged_count += 1
                    
        # Генерируем файлы мода
        self._generate_descriptor()
        self._generate_mod_file()
        self._generate_readme(result)
        
        result.success = result.failed_count == 0
        return result
    
    def _generate_descriptor(self):
        """Генерирует descriptor.mod"""
        content = f'''version="1.0.0"
tags={{
\t"Compatibility"
\t"Fixes"
}}
name="{self.patch_name}"
supported_version="1.15.*"
'''
        (self.output_path / "descriptor.mod").write_text(content, encoding='utf-8-sig')
        
    def _generate_mod_file(self):
        """Генерирует .mod файл для лаунчера"""
        safe_name = self.patch_name.replace(" ", "_").replace("+", "_")
        content = f'''version="1.0.0"
tags={{
\t"Compatibility"
\t"Fixes"
}}
name="{self.patch_name}"
supported_version="1.15.*"
path="mod/{self.output_path.name}"
'''
        (self.output_path / f"{safe_name}.mod").write_text(content, encoding='utf-8-sig')
        
    def _generate_readme(self, result: PatchResult):
        """Генерирует README"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        content = f"""# {self.patch_name}
Auto-generated compatibility patch
Created: {now}

## Statistics
- Merged files: {result.merged_count}
- Copied files: {result.copied_count}  
- Failed: {result.failed_count}

## Files
"""
        for f in result.files:
            status = "✓" if not f.has_conflicts else "⚠"
            content += f"\n{status} {f.relative_path}"
            content += f"\n  Type: {f.source_type}"
            content += f"\n  Sources: {', '.join(f.source_mods)}"
            if f.changes_count > 0:
                content += f"\n  Changes: {f.changes_count}"
            content += "\n"
            
        if result.errors:
            content += "\n## Errors\n"
            for e in result.errors:
                content += f"- {e}\n"
                
        content += """
## Installation
1. Copy this folder to your game's mod directory
2. Copy the .mod file to the same directory
3. Enable in the launcher AFTER all source mods

## Load Order
Place this patch LAST in your mod load order.
"""
        
        (self.output_path / "README.md").write_text(content, encoding='utf-8')
