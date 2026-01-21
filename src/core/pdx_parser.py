"""
Paradox Script Parser
Парсер скриптов Paradox с построением AST (дерева)

Поддерживает:
- Блоки: name = { ... }
- Списки: name = { item1 item2 item3 }
- Свойства: name = value
- Комментарии: # comment
- Вложенные структуры любой глубины
"""

import re
from typing import Dict, List, Union, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class NodeType(Enum):
    ROOT = "root"
    BLOCK = "block"           # name = { ... }
    PROPERTY = "property"     # name = value
    LIST_ITEM = "list_item"   # элемент списка
    COMMENT = "comment"       # # comment
    EMPTY_LINE = "empty"      # пустая строка


@dataclass
class PdxNode:
    """Узел AST"""
    node_type: NodeType
    name: str = ""
    value: str = ""
    children: List['PdxNode'] = field(default_factory=list)
    comment: str = ""  # Комментарий в конце строки
    is_commented: bool = False  # Весь узел закомментирован
    raw_line: str = ""  # Оригинальная строка для сохранения форматирования
    indent: str = ""  # Отступ
    
    def __hash__(self):
        return hash((self.node_type, self.name, self.value))
    
    def get_child(self, name: str) -> Optional['PdxNode']:
        """Получить дочерний узел по имени"""
        for child in self.children:
            if child.name == name:
                return child
        return None
    
    def get_children_by_name(self, name: str) -> List['PdxNode']:
        """Получить все дочерние узлы с указанным именем"""
        return [c for c in self.children if c.name == name]
    
    def has_child(self, name: str) -> bool:
        return any(c.name == name for c in self.children)
    
    def clone(self) -> 'PdxNode':
        """Глубокое копирование узла"""
        return PdxNode(
            node_type=self.node_type,
            name=self.name,
            value=self.value,
            children=[c.clone() for c in self.children],
            comment=self.comment,
            is_commented=self.is_commented,
            raw_line=self.raw_line,
            indent=self.indent
        )


class PdxParser:
    """Парсер Paradox скриптов"""
    
    def __init__(self):
        self.pos = 0
        self.lines: List[str] = []
        self.current_line = 0
    
    def parse(self, content: str) -> PdxNode:
        """Парсит контент и возвращает корневой узел AST"""
        # Нормализуем переносы строк
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        lines = content.split('\n')
        
        root = PdxNode(node_type=NodeType.ROOT, name="__root__")
        stack = [root]  # Стек открытых блоков
        
        for line_num, line in enumerate(lines):
            original_line = line
            
            # Определяем отступ
            stripped = line.strip()
            indent = line[:len(line) - len(stripped)] if stripped else ""
            
            # Пустая строка
            if not stripped:
                stack[-1].children.append(PdxNode(
                    node_type=NodeType.EMPTY_LINE,
                    raw_line=original_line,
                    indent=indent
                ))
                continue
            
            # Считаем скобки в активной части (без комментариев)
            line_for_braces = stripped
            hash_pos = self._find_comment_pos(stripped)
            if hash_pos >= 0:
                line_for_braces = stripped[:hash_pos]
            
            open_braces = line_for_braces.count('{')
            close_braces = line_for_braces.count('}')
            
            # Обрабатываем закрывающие скобки
            # Если строка начинается с } - закрываем блоки
            leading_close = 0
            temp = line_for_braces.lstrip()
            while temp.startswith('}'):
                leading_close += 1
                temp = temp[1:].lstrip()
            
            # Закрываем соответствующее количество блоков
            for _ in range(leading_close):
                if len(stack) > 1:
                    stack.pop()
            
            # Оставшаяся часть строки после закрывающих скобок
            remaining = stripped
            for _ in range(leading_close):
                pos = remaining.find('}')
                if pos >= 0:
                    remaining = remaining[pos+1:].strip()
            
            if not remaining:
                continue
            
            # Полностью закомментированная строка
            if remaining.startswith('#'):
                comment_content = remaining[1:].lstrip()
                # Проверяем - закомментированный блок?
                block_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:\s]*?)\s*=\s*\{', comment_content)
                if block_match:
                    # TODO: обработка закомментированных блоков
                    pass
                
                stack[-1].children.append(PdxNode(
                    node_type=NodeType.COMMENT,
                    value=remaining,
                    raw_line=original_line,
                    indent=indent
                ))
                continue
            
            # Проверяем на блок: name = { 
            block_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:\s]*?)\s*=\s*\{(.*)$', remaining)
            if block_match:
                name = block_match.group(1).strip()
                rest = block_match.group(2)
                
                # Комментарий
                comment = ""
                rest_hash = self._find_comment_pos(rest)
                if rest_hash >= 0:
                    comment = rest[rest_hash:].strip()
                    rest = rest[:rest_hash]
                
                rest = rest.strip()
                
                # Однострочный блок?
                if rest.endswith('}'):
                    # name = { content }
                    inner = rest[:-1].strip()
                    node = PdxNode(
                        node_type=NodeType.BLOCK,
                        name=name,
                        comment=comment,
                        raw_line=original_line,
                        indent=indent
                    )
                    if inner:
                        node.children = self._parse_inline_content(inner)
                    stack[-1].children.append(node)
                else:
                    # Многострочный блок - открываем
                    node = PdxNode(
                        node_type=NodeType.BLOCK,
                        name=name,
                        comment=comment,
                        raw_line=original_line,
                        indent=indent
                    )
                    stack[-1].children.append(node)
                    stack.append(node)  # Входим внутрь блока
                continue
            
            # Проверяем на свойство: name = value
            prop_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:]*)\s*=\s*(.+)$', remaining)
            if prop_match:
                name = prop_match.group(1).strip()
                value = prop_match.group(2).strip()
                
                comment = ""
                val_hash = self._find_comment_pos(value)
                if val_hash >= 0:
                    comment = value[val_hash:].strip()
                    value = value[:val_hash].strip()
                
                stack[-1].children.append(PdxNode(
                    node_type=NodeType.PROPERTY,
                    name=name,
                    value=value,
                    comment=comment,
                    raw_line=original_line,
                    indent=indent
                ))
                continue
            
            # Элемент списка или неизвестное
            list_match = re.match(r'^([a-zA-Z0-9_\.:]+)(.*)$', remaining)
            if list_match:
                value = list_match.group(1)
                rest = list_match.group(2).strip()
                comment = rest if rest.startswith('#') else ""
                
                stack[-1].children.append(PdxNode(
                    node_type=NodeType.LIST_ITEM,
                    value=value,
                    comment=comment,
                    raw_line=original_line,
                    indent=indent
                ))
                continue
            
            # Не распознали
            stack[-1].children.append(PdxNode(
                node_type=NodeType.COMMENT,
                value=remaining,
                raw_line=original_line,
                indent=indent
            ))
        
        return root
    
    def _parse_line(self) -> Optional[PdxNode]:
        """Парсит текущую строку и возвращает узел"""
        if self.current_line >= len(self.lines):
            return None
        
        line = self.lines[self.current_line]
        original_line = line
        
        # Определяем отступ
        indent = ""
        stripped = line.lstrip()
        if stripped:
            indent = line[:len(line) - len(stripped)]
        
        # Пустая строка
        if not stripped:
            self.current_line += 1
            return PdxNode(
                node_type=NodeType.EMPTY_LINE,
                raw_line=original_line,
                indent=indent
            )
        
        # Полностью закомментированная строка
        if stripped.startswith('#'):
            # Проверяем - это закомментированный блок?
            comment_content = stripped[1:].lstrip()
            block_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:\s]*?)\s*=\s*\{', comment_content)
            
            if block_match:
                # Закомментированный блок - парсим его
                return self._parse_commented_block(original_line, indent, block_match.group(1).strip())
            else:
                # Обычный комментарий
                self.current_line += 1
                return PdxNode(
                    node_type=NodeType.COMMENT,
                    value=stripped,
                    raw_line=original_line,
                    indent=indent
                )
        
        # Проверяем на блок: name = {
        block_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:\s]*?)\s*=\s*\{(.*)$', stripped)
        if block_match:
            name = block_match.group(1).strip()
            rest = block_match.group(2)
            
            # Извлекаем комментарий в конце строки
            comment = ""
            if '#' in rest:
                hash_pos = rest.find('#')
                comment = rest[hash_pos:].strip()
                rest = rest[:hash_pos].strip()
            
            # Проверяем - однострочный блок?
            if rest.rstrip().endswith('}'):
                # Однострочный блок: name = { content }
                content = rest.rstrip()[:-1].strip()
                self.current_line += 1
                
                node = PdxNode(
                    node_type=NodeType.BLOCK,
                    name=name,
                    comment=comment,
                    raw_line=original_line,
                    indent=indent
                )
                
                # Парсим содержимое однострочного блока
                if content:
                    node.children = self._parse_inline_content(content)
                
                return node
            else:
                # Многострочный блок
                self.current_line += 1
                return self._parse_block(name, comment, original_line, indent)
        
        # Проверяем на свойство: name = value
        prop_match = re.match(r'^([a-zA-Z0-9_][a-zA-Z0-9_\.:]*)\s*=\s*(.+)$', stripped)
        if prop_match:
            name = prop_match.group(1).strip()
            value = prop_match.group(2).strip()
            
            # Извлекаем комментарий
            comment = ""
            if '#' in value:
                hash_pos = value.find('#')
                comment = value[hash_pos:].strip()
                value = value[:hash_pos].strip()
            
            self.current_line += 1
            return PdxNode(
                node_type=NodeType.PROPERTY,
                name=name,
                value=value,
                comment=comment,
                raw_line=original_line,
                indent=indent
            )
        
        # Проверяем на элемент списка (просто значение)
        # Это может быть event_name, yes, no, число и т.д.
        list_match = re.match(r'^([a-zA-Z0-9_\.:]+)(.*)$', stripped)
        if list_match:
            value = list_match.group(1)
            rest = list_match.group(2).strip()
            
            comment = ""
            if rest.startswith('#'):
                comment = rest
            
            self.current_line += 1
            return PdxNode(
                node_type=NodeType.LIST_ITEM,
                value=value,
                comment=comment,
                raw_line=original_line,
                indent=indent
            )
        
        # Не распознали - сохраняем как есть
        self.current_line += 1
        return PdxNode(
            node_type=NodeType.COMMENT,
            value=stripped,
            raw_line=original_line,
            indent=indent
        )
    
    def _parse_block(self, name: str, comment: str, opening_line: str, indent: str) -> PdxNode:
        """Парсит многострочный блок"""
        node = PdxNode(
            node_type=NodeType.BLOCK,
            name=name,
            comment=comment,
            raw_line=opening_line,
            indent=indent
        )
        
        brace_depth = 1
        
        while self.current_line < len(self.lines) and brace_depth > 0:
            line = self.lines[self.current_line]
            stripped = line.strip()
            
            # Считаем скобки (без учёта комментариев)
            line_for_braces = line
            hash_pos = self._find_comment_pos(line)
            if hash_pos >= 0:
                line_for_braces = line[:hash_pos]
            
            open_count = line_for_braces.count('{')
            close_count = line_for_braces.count('}')
            
            # Проверяем - это закрывающая скобка нашего блока?
            new_depth = brace_depth + open_count - close_count
            
            if new_depth <= 0:
                # Блок закончился
                self.current_line += 1
                break
            
            brace_depth = new_depth
            
            # Парсим содержимое (важно: _parse_line сам двигает current_line)
            child = self._parse_line()
            if child:
                node.children.append(child)
        
        return node
    
    def _parse_commented_block(self, opening_line: str, indent: str, name: str) -> PdxNode:
        """Парсит закомментированный блок"""
        node = PdxNode(
            node_type=NodeType.BLOCK,
            name=name,
            is_commented=True,
            raw_line=opening_line,
            indent=indent
        )
        
        self.current_line += 1
        brace_depth = 1
        
        while self.current_line < len(self.lines) and brace_depth > 0:
            line = self.lines[self.current_line]
            stripped = line.strip()
            
            # Для закомментированного блока считаем скобки во всей строке
            brace_depth += stripped.count('{') - stripped.count('}')
            
            if brace_depth <= 0:
                self.current_line += 1
                break
            
            # Добавляем строку как comment node
            node.children.append(PdxNode(
                node_type=NodeType.COMMENT,
                value=stripped,
                raw_line=line,
                indent=line[:len(line) - len(stripped)] if stripped else ""
            ))
            
            self.current_line += 1
        
        return node
    
    def _parse_inline_content(self, content: str) -> List[PdxNode]:
        """Парсит содержимое однострочного блока"""
        children = []
        content = content.strip()
        
        if not content:
            return children
        
        # Разбиваем с учётом = и вложенных скобок
        i = 0
        while i < len(content):
            # Пропускаем пробелы
            while i < len(content) and content[i] in ' \t':
                i += 1
            
            if i >= len(content):
                break
            
            # Читаем токен (до пробела, = или {)
            token_start = i
            while i < len(content) and content[i] not in ' \t={}':
                i += 1
            
            token = content[token_start:i].strip()
            if not token:
                i += 1
                continue
            
            # Пропускаем пробелы
            while i < len(content) and content[i] in ' \t':
                i += 1
            
            # Проверяем что дальше
            if i < len(content) and content[i] == '=':
                i += 1  # skip =
                
                # Пропускаем пробелы после =
                while i < len(content) and content[i] in ' \t':
                    i += 1
                
                if i < len(content) and content[i] == '{':
                    # Вложенный блок: name = { ... }
                    i += 1  # skip {
                    depth = 1
                    block_start = i
                    
                    while i < len(content) and depth > 0:
                        if content[i] == '{':
                            depth += 1
                        elif content[i] == '}':
                            depth -= 1
                        i += 1
                    
                    block_content = content[block_start:i-1].strip()
                    
                    child = PdxNode(
                        node_type=NodeType.BLOCK,
                        name=token
                    )
                    if block_content:
                        child.children = self._parse_inline_content(block_content)
                    children.append(child)
                else:
                    # Свойство: name = value
                    value_start = i
                    while i < len(content) and content[i] not in ' \t{}':
                        i += 1
                    
                    value = content[value_start:i].strip()
                    children.append(PdxNode(
                        node_type=NodeType.PROPERTY,
                        name=token,
                        value=value
                    ))
            else:
                # Просто значение (элемент списка)
                children.append(PdxNode(
                    node_type=NodeType.LIST_ITEM,
                    value=token
                ))
        
        return children
    
    def _tokenize_inline(self, content: str) -> List[str]:
        """Разбивает inline контент на токены с учётом вложенных скобок"""
        tokens = []
        current = ""
        depth = 0
        
        for char in content:
            if char == '{':
                depth += 1
                current += char
            elif char == '}':
                depth -= 1
                current += char
            elif char in ' \t' and depth == 0:
                if current.strip():
                    tokens.append(current.strip())
                current = ""
            else:
                current += char
        
        if current.strip():
            tokens.append(current.strip())
        
        return tokens
    
    def _find_comment_pos(self, line: str) -> int:
        """Находит позицию комментария вне кавычек"""
        in_quotes = False
        for i, char in enumerate(line):
            if char == '"' and (i == 0 or line[i-1] != '\\'):
                in_quotes = not in_quotes
            elif char == '#' and not in_quotes:
                return i
        return -1


class PdxSerializer:
    """Сериализатор AST обратно в текст"""
    
    def serialize(self, node: PdxNode, indent_level: int = 0) -> str:
        """Сериализует AST в текст"""
        lines = []
        
        for child in node.children:
            serialized = self._serialize_node(child, indent_level)
            if serialized is not None:
                lines.append(serialized)
        
        return '\n'.join(lines)
    
    def _serialize_node(self, node: PdxNode, indent_level: int) -> Optional[str]:
        """Сериализует один узел"""
        indent = '\t' * indent_level
        
        if node.node_type == NodeType.EMPTY_LINE:
            return ""
        
        if node.node_type == NodeType.COMMENT:
            # Если есть raw_line - используем её
            if node.raw_line:
                return node.raw_line.rstrip('\r\n')
            return f"{indent}{node.value}"
        
        if node.node_type == NodeType.PROPERTY:
            line = f"{indent}{node.name} = {node.value}"
            if node.comment:
                line += f" {node.comment}"
            return line
        
        if node.node_type == NodeType.LIST_ITEM:
            line = f"{indent}{node.value}"
            if node.comment:
                line += f" {node.comment}"
            return line
        
        if node.node_type == NodeType.BLOCK:
            if node.is_commented:
                # Закомментированный блок - используем raw если есть
                if node.raw_line:
                    lines = [node.raw_line.rstrip('\r\n')]
                    for child in node.children:
                        if child.raw_line:
                            lines.append(child.raw_line.rstrip('\r\n'))
                    lines.append(f"{indent}#}}")
                    return '\n'.join(lines)
                else:
                    lines = [f"{indent}#{node.name} = {{"]
                    for child in node.children:
                        child_ser = self._serialize_node(child, indent_level + 1)
                        if child_ser:
                            lines.append(child_ser)
                    lines.append(f"{indent}#}}")
                    return '\n'.join(lines)
            
            # Обычный блок
            header = f"{indent}{node.name} = {{"
            if node.comment:
                header += f" {node.comment}"
            
            if not node.children:
                return f"{header} }}"
            
            # Проверяем - можно ли сделать однострочным?
            if self._can_be_inline(node):
                content = ' '.join(self._inline_child(c) for c in node.children if c.node_type not in (NodeType.EMPTY_LINE, NodeType.COMMENT))
                return f"{header} {content} }}"
            
            lines = [header]
            for child in node.children:
                child_ser = self._serialize_node(child, indent_level + 1)
                if child_ser is not None:
                    lines.append(child_ser)
            lines.append(f"{indent}}}")
            
            return '\n'.join(lines)
        
        return None
    
    def _can_be_inline(self, node: PdxNode) -> bool:
        """Проверяет можно ли сериализовать блок в одну строку"""
        # Подсчитываем реальные элементы
        real_children = [c for c in node.children if c.node_type not in (NodeType.EMPTY_LINE, NodeType.COMMENT)]
        
        if len(real_children) > 8:
            return False
        
        for child in real_children:
            if child.node_type == NodeType.BLOCK:
                # Вложенный блок можно inline только если он тоже простой
                if not self._can_be_inline(child):
                    return False
        
        return True
    
    def _inline_child(self, node: PdxNode) -> str:
        """Сериализует узел для inline"""
        if node.node_type == NodeType.PROPERTY:
            return f"{node.name} = {node.value}"
        if node.node_type == NodeType.LIST_ITEM:
            return node.value
        if node.node_type == NodeType.BLOCK:
            if not node.children:
                return f"{node.name} = {{ }}"
            content = ' '.join(self._inline_child(c) for c in node.children if c.node_type not in (NodeType.EMPTY_LINE, NodeType.COMMENT))
            return f"{node.name} = {{ {content} }}"
        return ""
