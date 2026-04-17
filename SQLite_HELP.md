Да, в SQLite есть отличные shortcut'ы! Это специальные **dot-команды** (мета-команды), которые начинаются с точки .

## Самые полезные команды для быстрой работы

### 1. Настройка форматирования (сделайте один раз и забудьте)

Эти команды нужно выполнить **один раз за сессию**, и все `SELECT` будут выглядеть красиво:

```bash
sqlite> .mode column      # выравнивание колонками
sqlite> .headers on       # показывать заголовки таблиц
```

Теперь `SELECT * FROM payments;` покажет аккуратную таблицу, а не кашу с разделителями `|` .

### 2. Просмотр таблиц без SELECT

```bash
sqlite> .tables          # список всех таблиц в базе
sqlite> .schema          # структура всей базы (CREATE TABLE команды)
sqlite> .schema payments # структура конкретной таблицы
```

### 3. Автоматизация при запуске (главный shortcut!)

Создайте файл `~/.sqliterc` (Linux/Mac) или `%USERPROFILE%\.sqliterc` (Windows) с вашими любимыми настройками :

```
-- ~/.sqliterc
.headers on
.mode column
.timer on
```

После этого **каждый раз**, когда вы запускаете `sqlite3 payments.db`, эти настройки применяются автоматически. Вам останется только писать `SELECT * FROM payments;` .

### 4. Быстрое выполнение команд из файла

Создайте файл `queries.sql`:

```sql
-- queries.sql
.headers on
.mode column
SELECT * FROM payments ORDER BY created_at DESC LIMIT 10;
```

И запускайте одной командой:

```bash
sqlite3 payments.db < queries.sql
# или внутри sqlite3:
sqlite> .read queries.sql
```

### 5. Для особо ленивых: однострочники в терминале

```bash
# Прямо из командной строки, без входа в sqlite3
sqlite3 payments.db "SELECT * FROM payments;"

# С красивым форматированием
sqlite3 -column -header payments.db "SELECT * FROM payments;"

# В line-режиме (каждая запись с новой строки)
sqlite3 -line payments.db "SELECT * FROM payments;"
```

## Ваш типичный рабочий процесс

**Вариант А (настроили .sqliterc один раз):**
```bash
$ sqlite3 payments.db
sqlite> .tables                    # посмотреть таблицы
payments
sqlite> SELECT * FROM payments;    # уже красиво отформатировано
sqlite> .quit
```

**Вариант Б (быстрый чек без захода в shell):**
```bash
sqlite3 -column -header payments.db "SELECT * FROM payments;"
```

**Вариант В (часто используемые сложные запросы):**
```bash
# Создайте файл ~/sql_shortcuts/recent.sql
sqlite3 payments.db .read ~/sql_shortcuts/recent.sql
```

## Полный список полезных dot-команд

| Команда | Что делает |
|---------|------------|
| `.tables` | Список всех таблиц |
| `.schema payments` | Показать структуру таблицы payments |
| `.databases` | Показать какие базы открыты |
| `.quit` или `.exit` | Выйти из sqlite3 |
| `.output file.txt` | Сохранить вывод в файл |
| `.output stdout` | Вернуть вывод обратно на экран |
| `.read file.sql` | Выполнить SQL из файла |
| `.backup backup.db` | Создать копию базы |

[source: 1, 4, 7]

Самый главный лайфхак: **настройте `.sqliterc` один раз**, и больше никогда не вводите `.mode column` и `.headers on` вручную.