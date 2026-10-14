# Повторение восстановления

## Принципы

1. Сохранить исходный ZIP и его SHA-256. Не работать с единственной копией.
2. Инвентаризировать `.frm`, `.MYD`, `.MYI`; отсутствующий `.MYD` не объявлять пустой таблицей.
3. Для этого архива все 266 FRM имеют engine byte `9` (MyISAM). InnoDB-файлы не являются резервной копией этих таблиц. Для другого движка остановиться и выбрать отдельную процедуру.
4. Старый сервер запускать только под непривилегированным пользователем, с Unix socket, `--skip-networking`, без журнала репликации и событий. Не давать другим пользователям доступ к рабочему каталогу. `--skip-grant-tables` допустим только в такой одноразовой изоляции.
5. До публикации: полный `CHECK TABLE EXTENDED`, проверка неизменности `.MYD`, количества/значений строк, структур, размеров JSON, импорт логического дампа и браузерные тесты.

## Инструмент восстановления

Проверено с MySQL Community **5.5.62**, собранным из тега `mysql/mysql-server:mysql-5.5.62`, CMake 3.31.10, GCC 12, GNU Bison 3.8.2 и GNU m4. Для сайта этот инструмент не нужен. В репозитории нет бинарников MySQL, его исходников или рабочих datadir.

Обычная Linux-машина с `gcc`, `g++`, `make`, `m4`, `bison`, `curl`, Python 3 и venv:

```sh
# Из корня репозитория, OUT — новый каталог вне публичного сайта.
export OUT="$HOME/quantumcore-recovery"
scripts/build_legacy.sh "$OUT"
export PY="$OUT/venv/bin/python"
export SRC="$OUT/mysql-server-mysql-5.5.62"
export BIN="$OUT/mysql-build"
export WORK="$OUT/work"

"$PY" scripts/recover.py data.zip "$WORK" --myisamchk "$BIN/storage/myisam/myisamchk"
chmod 700 "$WORK"
```

Скрипт извлекает только MyISAM-файлы и `db.opt`; проверяет пути ZIP, движок, дубли и лимит распаковки. Журналы, PID-файлы, старые InnoDB-файлы и осиротевшие CSV не подключаются к серверу. `myisamchk` получает имя **без расширения**: в данной сборке вызов с `.MYI` ошибочно сравнивает inode индекса и данных и возвращает ошибку 140.

В отдельном терминале (оставить процесс на переднем плане):

```sh
"$BIN/sql/mysqld" --no-defaults \
  --basedir="$BIN" --datadir="$WORK/data" \
  --socket="$WORK/mysql.sock" --pid-file="$WORK/mysql.pid" \
  --log-error="$WORK/mysql.log" --lc-messages-dir="$BIN/sql/share" \
  --character-sets-dir="$SRC/sql/share/charsets" \
  --skip-networking --skip-grant-tables --default-storage-engine=MyISAM \
  --performance-schema=OFF --skip-log-bin --event-scheduler=DISABLED \
  --read-only --myisam-recover-options=OFF
```

Сборка отключает InnoDB; не добавляйте `--skip-innodb` (в этой конфигурации опция неизвестна). `--read-only` не препятствует административному `REPAIR` под root; безопасность обеспечивается одноразовой копией и отсутствием сети, а не только этим флагом.

Далее из другого терминала:

```sh
"$PY" scripts/upgrade_indexes.py --socket "$WORK/mysql.sock" --work "$WORK"
"$PY" scripts/recover_schema.py --socket "$WORK/mysql.sock" --work "$WORK"
"$PY" scripts/export.py --socket "$WORK/mysql.sock" \
  --inventory "$WORK/inventory.json" --output "$OUT/export" --report "$OUT/checks.json"
"$PY" -c 'import sys; from pathlib import Path; sys.path.insert(0,"scripts"); from validate import validate; validate(Path(sys.argv[1]))' "$OUT/export"
```

`upgrade_indexes.py` выполняет только `REPAIR TABLE … QUICK` при неуспешной проверке, требует неизменности SHA-256 `.MYD` и успешного повторного `CHECK TABLE EXTENDED`. Не использовать `--force`, восстановление с потерей строк или автоматическое создание «пустых» оригиналов.

`recover_schema.py` создаёт **отдельные** `recovery_schema_*` с копией FRM и искусственным пустым MYD, затем `REPAIR … USE_FRM` восстанавливает индекс для чтения схемы. Эти scratch-таблицы нужны только для `SHOW CREATE TABLE`/`SHOW FULL COLUMNS`; их строки не экспортируются, имена не появляются на сайте, статусы определяются инвентаризацией **исходного** архива. Позиция AUTO_INCREMENT, хранившаяся в недостающем индексе, может быть недоступна.

Экспорт не перезаписывает существующий каталог. Неожиданная ошибка останавливает процесс, итоговый каталог не публикуется как успешный. Новую версию `data/` переносить на сайт только после всех проверок. Для дополненного архива используйте новый рабочий каталог и новый экспорт: это исключает остаточные чанки предыдущей версии.

## Проверка логического переноса

Запустить **второй** такой же изолированный сервер с новым пустым datadir и отдельным socket. В datadir достаточно пустого каталога `mysql`, так как доступ отключён через `--skip-grant-tables`. Не направлять эту проверку на восстановленный исходник или production.

```sh
"$PY" scripts/test_roundtrip.py --socket /path/to/second/mysql.sock \
  --data "$OUT/export" --report "$OUT/roundtrip.json"
```

Скрипт отказывается импортировать, если целевые базы уже существуют. Он предназначен только для формата SQL, создаваемого `export.py`, не для произвольных SQL-файлов. Импортирует в `world`, `characters`, `realmd`, `legacy_mysql`; проверяет структуру колонок, `CHECK TABLE EXTENDED`, `COUNT(*)` и потоковый SHA-256 канонических значений **всех строк**, а не только примеры. У неполных таблиц сравнивает только восстановленную структуру и явно сохраняет статус отсутствия данных.

Для сетевого тестового экземпляра MariaDB предусмотрены `--host`, `--port`, `--user`; пароль передаётся через `MYSQL_TEST_PASSWORD`. CI использует одноразовый контейнер MariaDB 10.11.

После завершения остановить оба одноразовых сервера (SIGTERM / Ctrl+C). В публичный репозиторий попадают только проверенный статический экспорт, компактный логический SQL и отчёты — не рабочие datadir и инструменты сборки.
