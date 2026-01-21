#!/usr/bin/env python3
"""
Генератор иконки для Paradox Mod Patcher
Запустите: python generate_icon.py

Требует: pip install Pillow
"""

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow не установлен!")
    print("Установите: pip install Pillow")
    exit(1)

from pathlib import Path
import math


def create_icon():
    """Создаёт иконку приложения"""
    
    # Размеры для .ico файла
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    
    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Фон - скруглённый квадрат
        margin = size // 16
        radius = size // 6
        
        # Градиент фона (тёмно-синий к фиолетовому)
        for y in range(size):
            ratio = y / size
            r = int(45 + ratio * 30)
            g = int(45 + ratio * 20)
            b = int(80 + ratio * 60)
            for x in range(size):
                # Проверяем что внутри скруглённого квадрата
                in_rect = True
                
                # Углы
                corners = [
                    (margin + radius, margin + radius),  # top-left
                    (size - margin - radius - 1, margin + radius),  # top-right
                    (margin + radius, size - margin - radius - 1),  # bottom-left
                    (size - margin - radius - 1, size - margin - radius - 1)  # bottom-right
                ]
                
                if x < margin or x >= size - margin or y < margin or y >= size - margin:
                    in_rect = False
                elif x < margin + radius and y < margin + radius:
                    # Top-left corner
                    if math.sqrt((x - margin - radius)**2 + (y - margin - radius)**2) > radius:
                        in_rect = False
                elif x >= size - margin - radius and y < margin + radius:
                    # Top-right corner
                    if math.sqrt((x - size + margin + radius + 1)**2 + (y - margin - radius)**2) > radius:
                        in_rect = False
                elif x < margin + radius and y >= size - margin - radius:
                    # Bottom-left corner
                    if math.sqrt((x - margin - radius)**2 + (y - size + margin + radius + 1)**2) > radius:
                        in_rect = False
                elif x >= size - margin - radius and y >= size - margin - radius:
                    # Bottom-right corner
                    if math.sqrt((x - size + margin + radius + 1)**2 + (y - size + margin + radius + 1)**2) > radius:
                        in_rect = False
                
                if in_rect:
                    img.putpixel((x, y), (r, g, b, 255))
        
        # Символ патча/связи - две переплетающиеся стрелки
        center = size // 2
        arrow_size = size // 3
        line_width = max(1, size // 16)
        
        # Цвет - золотистый/оранжевый
        arrow_color = (255, 180, 50, 255)
        
        # Рисуем упрощённый символ мержа: ⇄ или переплетение
        if size >= 32:
            # Левая стрелка вправо
            draw.line([(center - arrow_size//2, center - arrow_size//4), 
                       (center + arrow_size//3, center - arrow_size//4)], 
                      fill=arrow_color, width=line_width)
            # Наконечник
            draw.polygon([
                (center + arrow_size//3, center - arrow_size//4 - line_width*2),
                (center + arrow_size//2, center - arrow_size//4),
                (center + arrow_size//3, center - arrow_size//4 + line_width*2)
            ], fill=arrow_color)
            
            # Правая стрелка влево
            draw.line([(center + arrow_size//2, center + arrow_size//4), 
                       (center - arrow_size//3, center + arrow_size//4)], 
                      fill=arrow_color, width=line_width)
            # Наконечник
            draw.polygon([
                (center - arrow_size//3, center + arrow_size//4 - line_width*2),
                (center - arrow_size//2, center + arrow_size//4),
                (center - arrow_size//3, center + arrow_size//4 + line_width*2)
            ], fill=arrow_color)
        else:
            # Для маленьких размеров - просто крест/плюс
            draw.line([(center - arrow_size//2, center), (center + arrow_size//2, center)], 
                      fill=arrow_color, width=line_width)
            draw.line([(center, center - arrow_size//2), (center, center + arrow_size//2)], 
                      fill=arrow_color, width=line_width)
        
        images.append(img)
    
    # Сохраняем как .ico
    output_path = Path(__file__).parent / "resources" / "icons" / "app.ico"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # ICO файл с несколькими размерами
    images[5].save(
        output_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1]
    )
    
    print(f"Иконка создана: {output_path}")
    
    # Также сохраняем PNG версию (256x256)
    png_path = output_path.with_suffix('.png')
    images[5].save(png_path, format='PNG')
    print(f"PNG версия: {png_path}")
    
    return output_path


if __name__ == "__main__":
    create_icon()
