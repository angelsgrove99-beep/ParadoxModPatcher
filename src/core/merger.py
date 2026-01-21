"""
Smart Mod Merger
Умный мерджер для конфликтующих файлов Paradox модов
"""

from collections import OrderedDict
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

try:
    from .parser import ParadoxParser, ParadoxSerializer, tree_to_comparable_string, parse_file
except ImportError:
    from parser import ParadoxParser, ParadoxSerializer, tree_to_comparable_string, parse_file


class MergeStrategy(Enum):
    """Стратегия мержа"""
    PRIORITY_WINS = "priority"  # Приоритетный мод перезаписывает
    BASE_WINS = "base"  # Базовый мод сохраняется
    SMART_MERGE = "smart"  # Умный мерж (блок по блоку)
    MANUAL = "manual"  # Требуется ручное разрешение


@dataclass
class MergeChange:
    """Информация об изменении при мерже"""
    key: str
    change_type: str  # 'added', 'modified', 'removed', 'conflict'
    base_value: Any = None
    priority_value: Any = None
    merged_value: Any = None
    source_mod: str = ""


@dataclass
class MergeResult:
    """Результат мержа файла"""
    success: bool
    merged_content: str = ""
    changes: List[MergeChange] = field(default_factory=list)
    conflicts: List[MergeChange] = field(default_factory=list)
    error: str = ""


class SmartMerger:
    """Умный мерджер для Paradox файлов"""
    
    def __init__(self, base_name: str = "Base", priority_name: str = "Priority"):
        self.base_name = base_name
        self.priority_name = priority_name
        self.changes: List[MergeChange] = []
        
    def merge_files(
        self, 
        base_path: Path, 
        priority_path: Path,
        strategy: MergeStrategy = MergeStrategy.SMART_MERGE
    ) -> MergeResult:
        """
        Мержит два файла
        
        Args:
            base_path: Путь к базовому файлу (больше контента)
            priority_path: Путь к приоритетному файлу (изменения применяются поверх)
            strategy: Стратегия мержа
            
        Returns:
            MergeResult с объединённым контентом
        """
        try:
            # Читаем файлы
            with open(base_path, 'r', encoding='utf-8-sig') as f:
                base_content = f.read()
            with open(priority_path, 'r', encoding='utf-8-sig') as f:
                priority_content = f.read()
                
            return self.merge_contents(base_content, priority_content, strategy)
            
        except Exception as e:
            return MergeResult(success=False, error=str(e))
    
    def merge_contents(
        self,
        base_content: str,
        priority_content: str,
        strategy: MergeStrategy = MergeStrategy.SMART_MERGE
    ) -> MergeResult:
        """Мержит содержимое двух файлов"""
        self.changes = []
        
        try:
            # Парсим оба файла
            base_tree = ParadoxParser(base_content).parse()
            priority_tree = ParadoxParser(priority_content).parse()
            
            if strategy == MergeStrategy.PRIORITY_WINS:
                merged_tree = self._merge_priority_wins(base_tree, priority_tree)
            elif strategy == MergeStrategy.BASE_WINS:
                merged_tree = self._merge_base_wins(base_tree, priority_tree)
            else:
                merged_tree = self._merge_smart(base_tree, priority_tree)
            
            # Сериализуем результат
            serializer = ParadoxSerializer()
            merged_content = serializer.serialize(merged_tree)
            
            # Разделяем изменения и конфликты
            conflicts = [c for c in self.changes if c.change_type == 'conflict']
            
            return MergeResult(
                success=len(conflicts) == 0,
                merged_content=merged_content,
                changes=self.changes,
                conflicts=conflicts
            )
            
        except Exception as e:
            return MergeResult(success=False, error=str(e))
    
    def _merge_smart(self, base_tree: OrderedDict, priority_tree: OrderedDict) -> OrderedDict:
        """Умный мерж: база + изменённые блоки из priority"""
        merged = OrderedDict()
        merged['__meta__'] = {'lines': {}, 'comments': []}
        
        # Все ключи из обоих файлов (сохраняем порядок из base)
        all_keys = list(base_tree.keys())
        for key in priority_tree.keys():
            if key not in all_keys and key != '__meta__':
                all_keys.append(key)
        
        for key in all_keys:
            if key == '__meta__':
                continue
                
            in_base = key in base_tree
            in_priority = key in priority_tree
            
            if in_base and in_priority:
                # Есть в обоих - сравниваем
                base_str = tree_to_comparable_string(base_tree[key])
                priority_str = tree_to_comparable_string(priority_tree[key])
                
                if base_str != priority_str:
                    # Разные - берём priority
                    merged[key] = priority_tree[key]
                    self.changes.append(MergeChange(
                        key=key,
                        change_type='modified',
                        base_value=base_tree[key],
                        priority_value=priority_tree[key],
                        merged_value=priority_tree[key],
                        source_mod=self.priority_name
                    ))
                else:
                    # Одинаковые - берём base
                    merged[key] = base_tree[key]
                    
            elif in_base:
                # Только в base - сохраняем
                merged[key] = base_tree[key]
                
            else:
                # Только в priority - добавляем
                merged[key] = priority_tree[key]
                self.changes.append(MergeChange(
                    key=key,
                    change_type='added',
                    priority_value=priority_tree[key],
                    merged_value=priority_tree[key],
                    source_mod=self.priority_name
                ))
                
        return merged
    
    def _merge_priority_wins(self, base_tree: OrderedDict, priority_tree: OrderedDict) -> OrderedDict:
        """Простой мерж: priority перезаписывает base"""
        merged = OrderedDict()
        merged['__meta__'] = {'lines': {}, 'comments': []}
        
        # Сначала всё из base
        for key, value in base_tree.items():
            if key != '__meta__':
                merged[key] = value
                
        # Потом перезаписываем из priority
        for key, value in priority_tree.items():
            if key != '__meta__':
                if key in merged:
                    self.changes.append(MergeChange(
                        key=key,
                        change_type='modified',
                        base_value=merged.get(key),
                        priority_value=value,
                        merged_value=value,
                        source_mod=self.priority_name
                    ))
                else:
                    self.changes.append(MergeChange(
                        key=key,
                        change_type='added',
                        priority_value=value,
                        merged_value=value,
                        source_mod=self.priority_name
                    ))
                merged[key] = value
                
        return merged
    
    def _merge_base_wins(self, base_tree: OrderedDict, priority_tree: OrderedDict) -> OrderedDict:
        """Простой мерж: base сохраняется, добавляем только новое из priority"""
        merged = OrderedDict()
        merged['__meta__'] = {'lines': {}, 'comments': []}
        
        # Всё из base
        for key, value in base_tree.items():
            if key != '__meta__':
                merged[key] = value
                
        # Добавляем только то, чего нет в base
        for key, value in priority_tree.items():
            if key != '__meta__' and key not in merged:
                merged[key] = value
                self.changes.append(MergeChange(
                    key=key,
                    change_type='added',
                    priority_value=value,
                    merged_value=value,
                    source_mod=self.priority_name
                ))
                
        return merged


class MultiModMerger:
    """Мерджер для множества модов"""
    
    def __init__(self):
        self.mods: List[Tuple[str, Path]] = []  # (name, path)
        
    def add_mod(self, name: str, path: Path, priority: int = None):
        """Добавляет мод в список для мержа"""
        if priority is not None:
            self.mods.insert(priority, (name, path))
        else:
            self.mods.append((name, path))
            
    def merge_all(self, relative_path: str) -> MergeResult:
        """
        Мержит один файл из всех модов
        
        Порядок: первый мод - база, остальные применяются последовательно
        """
        if len(self.mods) < 2:
            return MergeResult(success=False, error="Need at least 2 mods to merge")
            
        # Начинаем с первого мода
        base_name, base_path = self.mods[0]
        base_file = base_path / relative_path
        
        if not base_file.exists():
            return MergeResult(success=False, error=f"Base file not found: {base_file}")
            
        with open(base_file, 'r', encoding='utf-8-sig') as f:
            current_content = f.read()
            
        all_changes = []
        
        # Последовательно применяем изменения из остальных модов
        for mod_name, mod_path in self.mods[1:]:
            mod_file = mod_path / relative_path
            
            if not mod_file.exists():
                continue
                
            merger = SmartMerger(base_name="Previous", priority_name=mod_name)
            
            with open(mod_file, 'r', encoding='utf-8-sig') as f:
                mod_content = f.read()
                
            result = merger.merge_contents(current_content, mod_content)
            
            if result.success:
                current_content = result.merged_content
                all_changes.extend(result.changes)
            else:
                return result
                
        return MergeResult(
            success=True,
            merged_content=current_content,
            changes=all_changes
        )
