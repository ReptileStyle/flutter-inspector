# Flutter UI Inspector

CLI-инструмент для инспекции UI запущенного Flutter-приложения в debug-режиме.

## Для AI-агентов: какой режим использовать?

| Задача | Команда | Описание |
|--------|---------|----------|
| "Что на экране?" | `flutter-inspect --content` | Список текста и иконок с контекстом (~300 строк) |
| "Понять структуру" | `flutter-inspect --smart` | Фильтрованное дерево виджетов (~1700 строк) |
| "Почему тут отступ?" | `flutter-inspect --trace "текст"` | Путь от root до элемента с padding/constraints |
| "Нужно всё дерево" | `flutter-inspect --widgets` | Raw debugDumpApp (~4000 строк) |

### Примеры вывода

**--content** (лучший для "что ты видишь на экране?"):
```
Row(start) > Expanded > Column(start)
  → "Задача на сегодня"
Row(start) > Flexible
  → "12 апр 2019 / Основной проект" [gray]
  → Icon(U+0E018) [gray]
```

**--smart** (лучший для "какая структура экрана?"):
```
Scaffold
  Row(start/center)
    Expanded(flex:1)
      Column(start/center)
        [CardWithSwipes]
          Row(start/center)
            Padding(pad:0.0, 12.0, 15.0, 0.0)
              Text("Задача на сегодня")
```

**--trace "12 апр"** (лучший для "откуда отступ?"):
```
# Layout Trace: '12 апр'

Scaffold
  Row (align:start/center)
    Expanded (flex:1)
      Column (align:start/start)
        Container (pad:0.0, 6.0, 0.0, 0.0)   ← вот откуда 6px сверху
          Padding (pad:0.0, 6.0, 0.0, 0.0)
            Row (align:start/center)
              Flexible (flex:1)
                Text ("12 апр 2019 / Основной проект")
```

## Установка

```bash
cd ~/scripts/flutter_ui_inspector
python3 -m venv .venv
.venv/bin/pip install websocket-client
```

## Как это работает

```
Flutter App (debug) → VM Service → flutter-inspect → Filtered Output
```

1. **Flutter прокси** (`~/fvm/versions/3.35.5/bin/flutter`) перехватывает VM Service URI при `flutter run` и сохраняет в `/tmp/flutter_vm_service_uri`

2. **flutter-inspect** читает URI и подключается через WebSocket

3. Вызывает `ext.flutter.debugDumpApp` и фильтрует вывод

## Использование

**Полный путь:** `/home/igorkuzevanov/scripts/flutter-inspect`

**Важно для AI-агентов:**
- Приложение должно быть в **debug mode** (не profile!) — иначе widget tree недоступен
- **НЕ используй `--raw`** — даёт неудобный вывод

```bash
# Рекомендуемые режимы для агентов
/home/igorkuzevanov/scripts/flutter-inspect --widgets > /tmp/widgets.txt  # Полное дерево
/home/igorkuzevanov/scripts/flutter-inspect --content   # Что на экране?
/home/igorkuzevanov/scripts/flutter-inspect --smart     # Структура экрана
/home/igorkuzevanov/scripts/flutter-inspect --trace "Сегодня"  # Дебаг расположения

# Обработка вывода --widgets (строки длинные из-за дерева)
grep -n "Editor\|TableCell\|padding" /tmp/widgets.txt   # Поиск виджетов
sed -n '100,120p' /tmp/widgets.txt | sed 's/^.*│//' | sed 's/^[ │└├─]*//'  # Очистка префиксов

# Дополнительные опции
flutter-inspect --content --tokens     # + подсчёт токенов
flutter-inspect --content -q           # Тихий режим (без статуса подключения)
flutter-inspect --list                 # Список debug-сессий

# Указать URI вручную
flutter-inspect --uri ws://127.0.0.1:12345/TOKEN=/ws --content
```

## Требования

- Flutter app запущен через `flutter run` (запускает пользователь, не агент)
- Python 3.8+
- websocket-client

## Структура проекта

```
flutter_ui_inspector/
├── inspector.py              # CLI entry point
├── discovery.py              # VM Service URI discovery
├── extractors/
│   └── semantics.py          # VM Service client
└── formatters/
    ├── widget_filter.py      # Smart filtering (content/smart/trace)
    ├── compact.py            # Legacy text formats
    └── json_output.py        # JSON formats
```

## Troubleshooting

**"PROFILE MODE" / пустой вывод**
- Приложение запущено в profile mode — widget tree недоступен
- Перезапусти с `flutter run` (без `--profile`)

**"No Flutter debug app found"**
- Убедись что приложение запущено через `flutter run`
- Проверь: `cat /tmp/flutter_vm_service_uri`

**"Connection refused"**
- Приложение было закрыто или перезапущено
- Перезапусти `flutter run`

**Вывод слишком большой**
- Используй `--content` вместо `--widgets`
- Добавь `--tokens` чтобы видеть размер
