# Flutter UI Inspector

CLI-инструмент для инспекции UI запущенного Flutter-приложения в debug-режиме.
Автоматически подключается к приложению и выводит дерево виджетов для использования в контексте LLM.

## Как это работает

```
Flutter App (debug) → VM Service → flutter-inspect → Widget Tree
```

1. **Flutter прокси** (`/home/igorkuzevanov/fvm/versions/3.35.5/bin/flutter`) перехватывает VM Service URI при запуске приложения и сохраняет в `/tmp/flutter_vm_service_uri`

2. **flutter-inspect** читает этот URI и подключается к VM Service через WebSocket

3. Вызывает `ext.flutter.debugDumpApp` для получения дерева виджетов

## Установка

```bash
cd ~/scripts/flutter_ui_inspector
python3 -m venv .venv
.venv/bin/pip install websocket-client
```

## Использование

### Базовое использование

```bash
# Показать дерево виджетов (не требует TalkBack на устройстве)
flutter-inspect --widgets

# С подсчётом токенов
flutter-inspect --widgets --tokens

# JSON формат
flutter-inspect --widgets --json

# Тихий режим (только данные)
flutter-inspect --widgets -q
```

### Semantics Tree (требует TalkBack)

```bash
# Если на устройстве включён TalkBack - даёт более компактный вывод
flutter-inspect

# Raw dump
flutter-inspect --raw
```

### Другие команды

```bash
# Список найденных debug-сессий
flutter-inspect --list

# Указать URI вручную
flutter-inspect --uri ws://127.0.0.1:12345/TOKEN=/ws --widgets

# Следить за изменениями
flutter-inspect --widgets --watch
```

## Требования

- Flutter app запущен через `flutter run` (запускает пользователь, не агент)
- Python 3.8+
- websocket-client

## Ограничения

- **Semantics Tree** пустой если на устройстве не включён TalkBack/VoiceOver
- **Widget Tree** (`--widgets`) работает всегда, но более verbose
- Если app запущен через Android Studio, URI может не сохраниться в файл

## Структура

```
flutter_ui_inspector/
├── inspector.py          # CLI
├── discovery.py          # Поиск VM Service URI
├── extractors/
│   └── semantics.py      # VM Service клиент
└── formatters/
    ├── compact.py        # Текстовые форматы
    └── json_output.py    # JSON форматы
```

## Troubleshooting

**"No Flutter debug app found"**
- Убедись что приложение запущено через `flutter run`
- Проверь: `cat /tmp/flutter_vm_service_uri`

**"Semantics tree is empty"**
- Используй `--widgets` флаг
- Или включи TalkBack на устройстве

**"Connection refused"**
- Приложение было закрыто или перезапущено
- Перезапусти `flutter run`
