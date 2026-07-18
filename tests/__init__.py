"""Тестовый пакет."""

import sys
from pathlib import Path

# Добавляем путь к папке app
app_path = str(Path(__file__).parent.parent / 'app')
if app_path not in sys.path:
    sys.path.insert(0, app_path)
