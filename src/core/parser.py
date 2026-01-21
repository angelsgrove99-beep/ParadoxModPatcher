"""
Paradox Script Parser
Парсер для синтаксиса Paradox (CK3, EU4, HOI4, Stellaris)
"""

from collections import OrderedDict
from typing import Optional, Tuple, Any, List
from dataclasses import dataclass


@dataclass
class ParsedBlock:
    """Распарсенный блок с метаданными"""
    name: str
    content: OrderedDict
    start_line: int
    end_line: int
    raw_text: str


class ParadoxParser:
    """Парсер Paradox-синтаксиса в древовидную структуру"""
    
    def __init__(self, content: str, preserve_comments: bool = True):
        self.content = content
        self.pos = 0
        self.line = 1
        self.preserve_comments = preserve_comments
        self.comments: List[Tuple[int, str]] = []  # (line, comment_text)
        
    def parse(self) -> OrderedDict:
        """Парсит весь контент в дерево"""
        result = OrderedDict()
        result['__meta__'] = {
            'lines': {},
            'comments': [],
            'raw_blocks': {}
        }
        
        max_iterations = len(self.content) + 1000  # Защита от бесконечного цикла
        iterations = 0
        
        while self.pos < len(self.content):
            iterations += 1
            if iterations > max_iterations:
                break  # Аварийный выход
                
            old_pos = self.pos
            
            self.skip_whitespace()
            
            # Сохраняем комментарии
            if self.pos < len(self.content) and self.content[self.pos] == '#':
                comment = self.read_comment()
                if self.preserve_comments:
                    result['__meta__']['comments'].append((self.line, comment))
                # Пропускаем \n после комментария если есть
                if self.pos < len(self.content) and self.content[self.pos] == '\n':
                    self.pos += 1
                    self.line += 1
                continue
                
            if self.pos >= len(self.content):
                break
            
            # Защита от бесконечного цикла - если позиция не изменилась
            if self.pos == old_pos:
                self.pos += 1
                continue
                
            # Запоминаем начало блока
            block_start = self.pos
            block_start_line = self.line
            
            key, value, line_num = self.parse_entry()
            if key:
                # Сохраняем raw текст блока
                block_end = self.pos
                raw_text = self.content[block_start:block_end].strip()
                
                if key in result and key != '__meta__':
                    # Дублирующийся ключ - делаем список
                    if not isinstance(result[key], list):
                        result[key] = [result[key]]
                    result[key].append(value)
                else:
                    result[key] = value
                    result['__meta__']['lines'][key] = line_num
                    result['__meta__']['raw_blocks'][key] = raw_text
                    
        return result
    
    def skip_whitespace(self):
        """Пропускает пробелы и переносы строк"""
        while self.pos < len(self.content):
            c = self.content[self.pos]
            if c == '\n':
                self.pos += 1
                self.line += 1
            elif c in ' \t\r':
                self.pos += 1
            else:
                break
                
    def read_comment(self) -> str:
        """Читает комментарий до конца строки"""
        start = self.pos
        while self.pos < len(self.content) and self.content[self.pos] != '\n':
            self.pos += 1
        return self.content[start:self.pos]
                
    def parse_entry(self) -> Tuple[Optional[str], Any, int]:
        """Парсит одну запись key = value"""
        self.skip_whitespace()
        
        # Пропускаем комментарии
        while self.pos < len(self.content) and self.content[self.pos] == '#':
            self.read_comment()
            self.skip_whitespace()
            
        if self.pos >= len(self.content):
            return None, None, 0
            
        line_num = self.line
        
        # Читаем ключ
        key = self.read_token()
        if not key:
            return None, None, 0
            
        self.skip_whitespace()
        
        # Пропускаем комментарии между ключом и оператором
        while self.pos < len(self.content) and self.content[self.pos] == '#':
            self.read_comment()
            self.skip_whitespace()
        
        # Проверяем оператор (= или < или > или ?=)
        if self.pos < len(self.content) and self.content[self.pos] in '=<>?':
            op = self.content[self.pos]
            self.pos += 1
            if self.pos < len(self.content) and self.content[self.pos] == '=':
                op += '='
                self.pos += 1
        else:
            # Нет оператора - это может быть просто значение в списке
            return key, True, line_num
            
        self.skip_whitespace()
        
        # Пропускаем комментарии после оператора
        while self.pos < len(self.content) and self.content[self.pos] == '#':
            self.read_comment()
            self.skip_whitespace()
        
        # Читаем значение
        value = self.read_value()
        
        return key, value, line_num
        
    def read_token(self) -> str:
        """Читает токен (идентификатор или строку в кавычках)"""
        if self.pos >= len(self.content):
            return ""
            
        # Строка в кавычках
        if self.content[self.pos] == '"':
            return self.read_quoted_string()
            
        # Обычный идентификатор (включая спец символы вроде scope:actor)
        start = self.pos
        while self.pos < len(self.content):
            c = self.content[self.pos]
            if c in ' \t\r\n={}#<>':
                break
            self.pos += 1
            
        return self.content[start:self.pos]
        
    def read_quoted_string(self) -> str:
        """Читает строку в кавычках"""
        assert self.content[self.pos] == '"'
        self.pos += 1
        start = self.pos
        
        while self.pos < len(self.content):
            if self.content[self.pos] == '"':
                result = self.content[start:self.pos]
                self.pos += 1
                return f'"{result}"'
            if self.content[self.pos] == '\n':
                self.line += 1
            self.pos += 1
            
        return f'"{self.content[start:]}"'
        
    def read_value(self) -> Any:
        """Читает значение (токен или блок)"""
        self.skip_whitespace()
        if self.pos >= len(self.content):
            return ""
            
        # Блок в скобках
        if self.content[self.pos] == '{':
            return self.read_block()
            
        # Обычное значение
        return self.read_token()
        
    def read_block(self) -> OrderedDict:
        """Читает блок { ... }"""
        assert self.content[self.pos] == '{'
        self.pos += 1
        
        result = OrderedDict()
        result['__meta__'] = {'lines': {}, 'comments': []}
        
        max_iterations = len(self.content) + 100
        iterations = 0
        
        while self.pos < len(self.content):
            iterations += 1
            if iterations > max_iterations:
                break
                
            old_pos = self.pos
            self.skip_whitespace()
            
            # Комментарии внутри блока
            if self.pos < len(self.content) and self.content[self.pos] == '#':
                comment = self.read_comment()
                if self.preserve_comments:
                    result['__meta__']['comments'].append((self.line, comment))
                # Пропускаем \n после комментария
                if self.pos < len(self.content) and self.content[self.pos] == '\n':
                    self.pos += 1
                    self.line += 1
                continue
                
            if self.pos >= len(self.content):
                break
            if self.content[self.pos] == '}':
                self.pos += 1
                break
            
            # Защита от зависания
            if self.pos == old_pos:
                self.pos += 1
                continue
                
            key, value, line_num = self.parse_entry()
            if key:
                if key in result and key != '__meta__':
                    if not isinstance(result[key], list):
                        result[key] = [result[key]]
                    result[key].append(value)
                else:
                    result[key] = value
                    result['__meta__']['lines'][key] = line_num
                    
        return result


class ParadoxSerializer:
    """Сериализатор дерева обратно в Paradox-формат"""
    
    def __init__(self, indent_char: str = '\t', newline: str = '\n'):
        self.indent_char = indent_char
        self.newline = newline
        
    def serialize(self, tree: OrderedDict, indent: int = 0) -> str:
        """Конвертирует дерево обратно в текст"""
        lines = []
        prefix = self.indent_char * indent
        
        for key, value in tree.items():
            if key == '__meta__':
                continue
                
            if isinstance(value, dict):
                lines.append(f"{prefix}{key} = {{")
                lines.append(self.serialize(value, indent + 1))
                lines.append(f"{prefix}}}")
                if indent == 0:
                    lines.append("")  # Пустая строка между блоками верхнего уровня
            elif isinstance(value, list):
                for v in value:
                    if isinstance(v, dict):
                        lines.append(f"{prefix}{key} = {{")
                        lines.append(self.serialize(v, indent + 1))
                        lines.append(f"{prefix}}}")
                    else:
                        lines.append(f"{prefix}{key} = {v}")
            elif value is True:
                # Просто ключ без значения (в списках)
                lines.append(f"{prefix}{key}")
            else:
                lines.append(f"{prefix}{key} = {value}")
                
        return self.newline.join(lines)
    
    def serialize_with_comments(self, tree: OrderedDict, indent: int = 0) -> str:
        """Сериализует с сохранением комментариев"""
        # TODO: Более сложная логика с восстановлением комментариев
        return self.serialize(tree, indent)


def tree_to_comparable_string(tree: Any) -> str:
    """Конвертирует дерево в строку для сравнения (игнорируя форматирование)"""
    if isinstance(tree, dict):
        parts = []
        for k, v in tree.items():
            if k == '__meta__':
                continue
            parts.append(f"{k}={tree_to_comparable_string(v)}")
        return "{" + ",".join(sorted(parts)) + "}"
    elif isinstance(tree, list):
        return "[" + ",".join(tree_to_comparable_string(x) for x in tree) + "]"
    else:
        return str(tree)


def parse_file(filepath: str, encoding: str = 'utf-8-sig') -> OrderedDict:
    """Удобная функция для парсинга файла"""
    with open(filepath, 'r', encoding=encoding) as f:
        content = f.read()
    parser = ParadoxParser(content)
    return parser.parse()


def serialize_to_file(tree: OrderedDict, filepath: str, encoding: str = 'utf-8-sig'):
    """Удобная функция для записи дерева в файл"""
    serializer = ParadoxSerializer()
    content = serializer.serialize(tree)
    with open(filepath, 'w', encoding=encoding) as f:
        f.write(content)
