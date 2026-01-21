"""
Semantic Merger - Мержер с пониманием семантики Paradox скриптов

Ключевые правила:
1. События (namespace.XXX = {}) - АТОМАРНЫ. Берём целиком из одного мода.
2. Списки вызовов (on_actions, events в on_action) - МЕРЖАТСЯ.
3. Определения (scripted_trigger, scripted_effect) - АТОМАРНЫ.
4. Свойства (name = value) - последний мод побеждает.

Типы блоков:
- ATOMIC: Берётся целиком из одного источника (события, триггеры, эффекты)
- MERGEABLE_LIST: Списки вызовов - накапливаем уникальные элементы
- CONTAINER: Контейнер для других блоков (on_game_start содержит on_actions и events)
"""

import re
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum


class BlockType(Enum):
    """Тип блока по семантике"""
    ATOMIC = "atomic"              # Неделимый - берём целиком
    MERGEABLE_LIST = "list"        # Список вызовов - мержим элементы
    CONTAINER = "container"        # Контейнер - рекурсивно обрабатываем children
    PROPERTY = "property"          # Свойство name = value


# Блоки которые являются СПИСКАМИ ВЫЗОВОВ (можно мержить)
MERGEABLE_LIST_BLOCKS = {
    'on_actions',      # on_actions = { action1 action2 }
    'events',          # events = { event1 event2 } в on_action файлах
    'random_events',   # random_events = { ... }
}

# Блоки которые АТОМАРНЫ (нельзя мержить содержимое)
ATOMIC_BLOCKS = {
    'option',          # option внутри события
    'trigger',         # trigger = { } - условия
    'effect',          # effect = { } внутри события (не в on_action!)
    'immediate',       # immediate = { }
    'after',           # after = { }
    'desc',            # desc = { } или desc = "..."
    'left_portrait',   # portrait блоки
    'right_portrait',
    'lower_left_portrait',
    'lower_right_portrait',
    'artifact',
    'widget',
}

# Паттерны для определения типа файла
FILE_TYPE_PATTERNS = {
    'event': r'events[/\\]',           # events/*.txt
    'on_action': r'on_action[s]?[/\\]', # on_action/*.txt  
    'scripted_trigger': r'scripted_triggers[/\\]',
    'scripted_effect': r'scripted_effects[/\\]',
    'decision': r'decisions[/\\]',
    'other': r'.*',
}


@dataclass
class SemanticBlock:
    """Блок с семантической информацией"""
    name: str
    block_type: BlockType
    full_text: str
    inner_text: str
    children: Dict[str, 'SemanticBlock'] = field(default_factory=dict)
    list_items: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
    start_pos: int = 0
    end_pos: int = 0


@dataclass
class MergeChange:
    """Описание изменения"""
    path: str
    change_type: str
    mod_name: str
    content: str


@dataclass
class SemanticMergeResult:
    """Результат мержа"""
    success: bool
    content: str = ""
    error: str = ""
    changes: List[MergeChange] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SemanticMerger:
    """Мержер с пониманием семантики Paradox"""
    
    def __init__(self):
        self.changes: List[MergeChange] = []
        self.warnings: List[str] = []
        self.file_type: str = "other"
    
    def merge_file(self, base_path: Path, mod_paths: List[Tuple[str, Path]]) -> SemanticMergeResult:
        """Мержит файл с учётом семантики"""
        self.changes = []
        self.warnings = []
        
        # Определяем тип файла
        self.file_type = self._detect_file_type(str(base_path))
        
        try:
            with open(base_path, 'r', encoding='utf-8-sig') as f:
                base_content = f.read()
            
            mod_contents = []
            for mod_name, mod_path in mod_paths:
                with open(mod_path, 'r', encoding='utf-8-sig') as f:
                    mod_contents.append((mod_name, f.read()))
            
            return self.merge_contents(base_content, mod_contents)
            
        except Exception as e:
            return SemanticMergeResult(
                success=False,
                error=f"Ошибка чтения: {str(e)}"
            )
    
    def merge_contents(self, base_content: str, mod_contents: List[Tuple[str, str]]) -> SemanticMergeResult:
        """Мержит содержимое файлов"""
        try:
            base_content = base_content.replace('\r\n', '\n')
            mod_contents = [(n, c.replace('\r\n', '\n')) for n, c in mod_contents]
            
            # Парсим базу
            base_blocks = self._parse_blocks(base_content)
            
            # Результат начинаем с базы
            result_content = base_content
            
            # Собираем изменения из модов
            for mod_name, mod_content in mod_contents:
                mod_blocks = self._parse_blocks(mod_content)
                
                # Обрабатываем каждый блок мода
                for block_name, mod_block in mod_blocks.items():
                    if block_name.startswith('__'):
                        continue
                    
                    base_block = base_blocks.get(block_name)
                    
                    if base_block is None:
                        # Новый блок - добавляем целиком
                        result_content = self._add_new_block(result_content, mod_block, mod_name)
                    else:
                        # Существующий блок - мержим по семантике
                        result_content = self._merge_block(
                            result_content, base_block, mod_block, mod_name
                        )
            
            # Валидация результата
            validation_result = self._validate_result(result_content)
            if not validation_result[0]:
                return SemanticMergeResult(
                    success=False,
                    error=validation_result[1],
                    warnings=self.warnings
                )
            
            return SemanticMergeResult(
                success=True,
                content=result_content,
                changes=self.changes,
                warnings=self.warnings
            )
            
        except Exception as e:
            import traceback
            return SemanticMergeResult(
                success=False,
                error=f"Ошибка мержа: {str(e)}\n{traceback.format_exc()}"
            )
    
    def _detect_file_type(self, path: str) -> str:
        """Определяет тип файла по пути"""
        path = path.replace('\\', '/')
        
        if '/events/' in path:
            return 'event'
        if '/on_action' in path:
            return 'on_action'
        if '/scripted_triggers/' in path:
            return 'scripted_trigger'
        if '/scripted_effects/' in path:
            return 'scripted_effect'
        if '/decisions/' in path:
            return 'decision'
        
        return 'other'
    
    def _get_block_type(self, block_name: str, parent_type: Optional[str] = None) -> BlockType:
        """Определяет семантический тип блока"""
        
        # Проверяем на событие (namespace.XXX)
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*\.\d+$', block_name):
            return BlockType.ATOMIC  # События атомарны
        
        # Проверяем на числовой ID (province, title date)
        if re.match(r'^\d+$', block_name) or re.match(r'^\d+\.\d+\.\d+$', block_name):
            return BlockType.ATOMIC
        
        # Списки вызовов
        if block_name in MERGEABLE_LIST_BLOCKS:
            return BlockType.MERGEABLE_LIST
        
        # Атомарные блоки
        if block_name in ATOMIC_BLOCKS:
            return BlockType.ATOMIC
        
        # on_action контейнеры (on_game_start, on_birth, etc.)
        if block_name.startswith('on_') or block_name.endswith('_pulse'):
            return BlockType.CONTAINER
        
        # scripted_trigger/effect определения - атомарны
        if self.file_type in ('scripted_trigger', 'scripted_effect'):
            return BlockType.ATOMIC
        
        # По умолчанию - контейнер
        return BlockType.CONTAINER
    
    def _parse_blocks(self, content: str) -> Dict[str, SemanticBlock]:
        """Парсит блоки верхнего уровня"""
        blocks = {}
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            if not stripped or stripped.startswith('#'):
                i += 1
                continue
            
            # Ищем начало блока: name = {
            match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:]*)\s*=\s*\{', stripped)
            if match:
                block_name = match.group(1)
                start_line = i
                start_pos = sum(len(lines[j]) + 1 for j in range(i))
                
                # Находим конец блока
                brace_depth = 0
                block_lines = []
                
                while i < len(lines):
                    block_line = lines[i]
                    block_lines.append(block_line)
                    
                    line_for_count = self._remove_comments(block_line)
                    brace_depth += line_for_count.count('{') - line_for_count.count('}')
                    i += 1
                    
                    if brace_depth <= 0:
                        break
                
                full_text = '\n'.join(block_lines)
                inner_start = full_text.find('{') + 1
                inner_end = full_text.rfind('}')
                inner_text = full_text[inner_start:inner_end] if inner_end > inner_start else ""
                
                block_type = self._get_block_type(block_name)
                
                block = SemanticBlock(
                    name=block_name,
                    block_type=block_type,
                    full_text=full_text,
                    inner_text=inner_text,
                    start_pos=start_pos,
                    end_pos=start_pos + len(full_text)
                )
                
                # Парсим содержимое
                self._parse_block_contents(block)
                
                blocks[block_name] = block
            else:
                i += 1
        
        return blocks
    
    def _parse_block_contents(self, block: SemanticBlock):
        """Парсит содержимое блока"""
        if block.block_type == BlockType.ATOMIC:
            # Атомарный блок - не парсим глубже
            return
        
        content = block.inner_text
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            if not stripped or stripped.startswith('#'):
                i += 1
                continue
            
            # Вложенный блок
            match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:]*)\s*=\s*\{(.*)$', stripped)
            if match:
                child_name = match.group(1)
                rest = match.group(2)
                
                child_type = self._get_block_type(child_name, block.name)
                
                # Однострочный блок?
                if rest.rstrip().endswith('}'):
                    inner = rest.rstrip()[:-1].strip()
                    
                    child = SemanticBlock(
                        name=child_name,
                        block_type=child_type,
                        full_text=stripped,
                        inner_text=inner
                    )
                    
                    if child_type == BlockType.MERGEABLE_LIST:
                        child.list_items = self._extract_list_items(inner)
                    
                    block.children[child_name] = child
                    i += 1
                else:
                    # Многострочный
                    start_i = i
                    brace_depth = 1
                    child_lines = [line]
                    i += 1
                    
                    while i < len(lines) and brace_depth > 0:
                        child_line = lines[i]
                        child_lines.append(child_line)
                        line_for_count = self._remove_comments(child_line)
                        brace_depth += line_for_count.count('{') - line_for_count.count('}')
                        i += 1
                    
                    child_text = '\n'.join(child_lines)
                    inner_start = child_text.find('{') + 1
                    inner_end = child_text.rfind('}')
                    inner_text = child_text[inner_start:inner_end] if inner_end > inner_start else ""
                    
                    child = SemanticBlock(
                        name=child_name,
                        block_type=child_type,
                        full_text=child_text,
                        inner_text=inner_text
                    )
                    
                    if child_type == BlockType.MERGEABLE_LIST:
                        child.list_items = self._extract_list_items(inner_text)
                    elif child_type == BlockType.CONTAINER:
                        self._parse_block_contents(child)
                    
                    block.children[child_name] = child
                continue
            
            # Свойство или элемент списка
            if block.block_type == BlockType.MERGEABLE_LIST:
                # Элемент списка
                item_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:]*)', stripped)
                if item_match:
                    block.list_items.append(item_match.group(1))
            else:
                # Свойство
                prop_match = re.match(r'^([a-zA-Z0-9_]+)\s*=\s*(.+)$', stripped)
                if prop_match:
                    prop_name = prop_match.group(1)
                    prop_value = self._remove_comments(prop_match.group(2)).strip()
                    block.properties[prop_name] = prop_value
            
            i += 1
    
    def _extract_list_items(self, content: str) -> List[str]:
        """Извлекает элементы списка"""
        items = []
        clean = self._remove_comments(content)
        
        # Разбиваем по пробелам
        for token in clean.split():
            token = token.strip()
            if token and re.match(r'^[a-zA-Z0-9_][a-zA-Z0-9_\.:]*$', token):
                items.append(token)
        
        return items
    
    def _merge_block(self, content: str, base_block: SemanticBlock, 
                     mod_block: SemanticBlock, mod_name: str) -> str:
        """Мержит блок согласно его семантике"""
        
        if base_block.block_type == BlockType.ATOMIC:
            # Атомарный блок - проверяем изменился ли
            if self._normalize(base_block.inner_text) != self._normalize(mod_block.inner_text):
                # Заменяем целиком
                content = content.replace(base_block.full_text, mod_block.full_text, 1)
                self.changes.append(MergeChange(
                    path=base_block.name,
                    change_type='replaced_atomic',
                    mod_name=mod_name,
                    content=base_block.name
                ))
            return content
        
        if base_block.block_type == BlockType.MERGEABLE_LIST:
            # Список - добавляем уникальные элементы
            new_items = []
            for item in mod_block.list_items:
                if item not in base_block.list_items and item not in new_items:
                    new_items.append(item)
            
            if new_items:
                content = self._add_items_to_list(content, base_block, new_items)
                for item in new_items:
                    self.changes.append(MergeChange(
                        path=base_block.name,
                        change_type='added_item',
                        mod_name=mod_name,
                        content=item
                    ))
            return content
        
        if base_block.block_type == BlockType.CONTAINER:
            # Контейнер - рекурсивно обрабатываем children
            for child_name, mod_child in mod_block.children.items():
                base_child = base_block.children.get(child_name)
                
                if base_child is None:
                    # Новый дочерний блок
                    if mod_child.block_type != BlockType.ATOMIC:
                        # Добавляем только не-атомарные (списки)
                        content = self._add_child_to_block(content, base_block, mod_child)
                        self.changes.append(MergeChange(
                            path=f"{base_block.name}.{child_name}",
                            change_type='added_child',
                            mod_name=mod_name,
                            content=child_name
                        ))
                else:
                    # Рекурсивный мерж
                    content = self._merge_block(content, base_child, mod_child, mod_name)
            
            return content
        
        return content
    
    def _add_new_block(self, content: str, block: SemanticBlock, mod_name: str) -> str:
        """Добавляет новый блок в конец файла"""
        content = content.rstrip() + '\n\n' + block.full_text + '\n'
        self.changes.append(MergeChange(
            path=block.name,
            change_type='added_block',
            mod_name=mod_name,
            content=block.name
        ))
        return content
    
    def _add_items_to_list(self, content: str, block: SemanticBlock, new_items: List[str]) -> str:
        """Добавляет элементы в список"""
        # Находим блок в content
        pattern = rf'({re.escape(block.name)}\s*=\s*\{{)'
        match = re.search(pattern, content)
        
        if not match:
            return content
        
        start = match.end() - 1  # позиция {
        
        # Находим закрывающую скобку
        depth = 0
        end = start
        for i in range(start, len(content)):
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        
        inner = content[start + 1:end]
        
        # Определяем формат
        if '\n' in inner:
            # Многострочный
            indent = '\t\t'
            for line in inner.split('\n'):
                if line.strip() and not line.strip().startswith('#'):
                    indent = line[:len(line) - len(line.lstrip())]
                    break
            
            # Добавляем новые элементы перед закрывающей скобкой
            new_lines = '\n'.join(f'{indent}{item}' for item in new_items)
            
            # Вставляем перед последним }
            insert_pos = end
            new_content = content[:insert_pos] + new_lines + '\n' + content[insert_pos:]
        else:
            # Однострочный
            all_items = block.list_items + new_items
            new_inner = ' ' + ' '.join(all_items) + ' '
            new_content = content[:start] + '{' + new_inner + '}' + content[end + 1:]
        
        return new_content
    
    def _add_child_to_block(self, content: str, parent: SemanticBlock, child: SemanticBlock) -> str:
        """Добавляет дочерний блок"""
        # Находим родительский блок
        pattern = rf'({re.escape(parent.name)}\s*=\s*\{{)'
        match = re.search(pattern, content)
        
        if not match:
            return content
        
        start = match.end() - 1
        
        # Находим закрывающую скобку родителя
        depth = 0
        end = start
        for i in range(start, len(content)):
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        
        # Добавляем перед закрывающей скобкой
        indent = '\t'
        new_block = f'\n{indent}{child.full_text.strip()}\n'
        
        return content[:end] + new_block + content[end:]
    
    def _validate_result(self, content: str) -> Tuple[bool, str]:
        """Валидирует результат мержа"""
        # Проверка баланса скобок
        open_count = 0
        close_count = 0
        
        for line in content.split('\n'):
            clean = self._remove_comments(line)
            open_count += clean.count('{')
            close_count += clean.count('}')
        
        if open_count != close_count:
            return False, f"Несбалансированные скобки: {{ = {open_count}, }} = {close_count}"
        
        # Проверка структуры событий (если это event файл)
        if self.file_type == 'event':
            # Каждое событие должно иметь type, title/desc, хотя бы один option
            event_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*\.\d+)\s*=\s*\{'
            for match in re.finditer(event_pattern, content):
                event_name = match.group(1)
                # Находим содержимое события
                start = match.end() - 1
                depth = 0
                end = start
                for i in range(start, len(content)):
                    if content[i] == '{':
                        depth += 1
                    elif content[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                
                event_content = content[start:end + 1]
                
                # Проверяем наличие обязательных элементов
                if 'type' not in event_content:
                    self.warnings.append(f"Событие {event_name} не имеет 'type'")
                
                if 'option' not in event_content:
                    self.warnings.append(f"Событие {event_name} не имеет 'option'")
        
        return True, ""
    
    def _remove_comments(self, line: str) -> str:
        """Убирает комментарии из строки"""
        in_quotes = False
        for i, char in enumerate(line):
            if char == '"' and (i == 0 or line[i-1] != '\\'):
                in_quotes = not in_quotes
            elif char == '#' and not in_quotes:
                return line[:i]
        return line
    
    def _normalize(self, text: str) -> str:
        """Нормализует текст для сравнения"""
        lines = []
        for line in text.split('\n'):
            line = self._remove_comments(line).strip()
            if line:
                lines.append(line)
        return ' '.join(lines).replace('\t', ' ').replace('  ', ' ')
