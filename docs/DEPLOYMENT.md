# Запуск Relayix через Docker Compose

Все переменные установки задаются **в одном файле**:

```text
../private/relayix-config/deployment.json
```

Путь указан относительно папки репозитория. Файл создаёт `scripts/write_config.py`; редактировать Compose-файлы и создавать `.env` не нужно. Пароли и токены остаются вне Git. Все значения в JSON записывайте строками, включая порты и `true`/`false`.

## 1. Подготовить образ

Нужны Git, Docker Engine с Docker Compose v2, Python 3.10+ и доступ пользователя к Docker.

```bash
git clone https://github.com/devops-nechaev/Relayix.git
cd Relayix
docker compose version
```

Соберите образ из текущих исходников. Rust и Node.js на хост устанавливать не требуется: сборка выполняется внутри Docker.

```bash
docker build --pull -t relayix:0.6.1 .
```

Если у вас уже есть опубликованный образ в реестре, вместо сборки выполните `docker pull` для его адреса и укажите этот адрес в `RELAYIX_IMAGE` в приватном JSON. Локальный тег `relayix:0.6.1` сам по себе не скачивает образ из GitHub. GHCR-публикация описана в [GITHUB.md](GITHUB.md).

## 2. Выбрать, где находится PostgreSQL

| Вариант | `DATABASE_MODE` | Что запустит Compose |
| --- | --- | --- |
| Новая PostgreSQL в этой же установке Compose | `local` | `app` и `db`; данные в Docker volume |
| Готовая PostgreSQL на другом сервере | `external` | Только `app` |
| Готовая PostgreSQL на хосте Docker | `external` | Только `app`; хост базы — `host.docker.internal` |

### Вариант A: база внутри Compose

Для **новой** установки:

```bash
python3 scripts/write_config.py ../private/relayix-config/deployment.json --database local --generate
nano ../private/relayix-config/deployment.json
```

Генератор уже заполнит пароль PostgreSQL, пароль администратора и API-токен. Обычно достаточно проверить следующие поля:

```json
{
  "DATABASE_MODE": "local",
  "RELAYIX_IMAGE": "relayix:0.6.1",
  "COMPOSE_PROJECT_NAME": "relayix",
  "BIND_ADDRESS": "127.0.0.1",
  "PORT": "8080",
  "POSTGRES_USER": "relayix",
  "POSTGRES_DB": "relayix"
}
```

Это фрагмент настроек: измените соответствующие поля **в сгенерированном файле**, сохранив пароли и остальные значения. `POSTGRES_HOST`, `POSTGRES_PORT` и настройки TLS в режиме `local` не нужны: приложение подключается к `db:5432` внутри сети Compose. Порт PostgreSQL на хост не публикуется.

`BIND_ADDRESS=127.0.0.1` открывает интерфейс только на хосте. Для доступа с другого компьютера укажите IP нужного сетевого интерфейса или `0.0.0.0` и используйте в браузере адрес сервера.

Запуск:

```bash
scripts/compose.sh up -d
scripts/compose.sh ps
curl --fail http://127.0.0.1:8080/healthz
```

Откройте `http://127.0.0.1:8080` на хосте и войдите с `ADMIN_USERNAME` / `ADMIN_PASSWORD` из приватного JSON. Если меняли адрес или порт, используйте свои значения в браузере и `curl`.

При повторном запуске используйте **тот же файл**, пароль, имя проекта и том. Скрипт генерации намеренно отказывается перезаписывать существующий файл. Изменение `POSTGRES_PASSWORD` в JSON не меняет пароль роли в уже созданной базе.

### Вариант B: готовая удалённая база

На сервере PostgreSQL заранее должны существовать база и роль, которой разрешено подключение и создание/изменение объектов в этой базе. Relayix применяет SQL-миграции при запуске; саму внешнюю базу или роль он не создаёт.

```bash
python3 scripts/write_config.py ../private/relayix-config/deployment.json --database external --generate
nano ../private/relayix-config/deployment.json
```

Генератор создаст учётные данные администратора Relayix, но **не придумает пароль существующей базы**. Заполните эти поля в созданном файле:

```json
{
  "DATABASE_MODE": "external",
  "POSTGRES_HOST": "postgres.example.org",
  "POSTGRES_PORT": "5432",
  "POSTGRES_USER": "relayix",
  "POSTGRES_DB": "relayix",
  "POSTGRES_PASSWORD": "REPLACE_WITH_THE_EXISTING_DATABASE_PASSWORD",
  "POSTGRES_SSLMODE": "verify-full",
  "POSTGRES_SSLROOTCERT": ""
}
```

Указывайте в `POSTGRES_HOST` только имя или IP, без `postgres://`, порта и пути. Пароль вводится обычной JSON-строкой; URL-кодирование символов `@`, `#`, `%` и других скрипт выполнит сам.

Если провайдер выдал CA-сертификат, сохраните его на Docker-хосте и задайте **абсолютный путь**:

```json
{
  "POSTGRES_SSLROOTCERT": "/srv/relayix-private/postgres-ca.crt"
}
```

Используется публичный сертификат CA, не приватный ключ. Файл должен быть доступен для чтения пользователю контейнера. Скрипт подключит его только для чтения к приложению и инструментам базы. При `verify-full` имя `POSTGRES_HOST` должно соответствовать сертификату сервера. Без своего CA используются доверенные корневые сертификаты клиента.

`verify-full` проверяет TLS и имя сервера. Если сервер намеренно работает без TLS в доверенной сети, явно задайте `POSTGRES_SSLMODE=disable`. Доступны также `require`, `verify-ca`, `prefer` и `allow`; для `verify-ca` укажите CA-файл. Значение `require` шифрует соединение, но не заменяет проверку имени сервера. [Режимы TLS PostgreSQL](https://www.postgresql.org/docs/17/libpq-ssl.html).

После заполнения настроек команды такие же:

```bash
scripts/compose.sh up -d
scripts/compose.sh ps
scripts/compose.sh logs --tail=50 app
curl --fail http://127.0.0.1:8080/healthz
```

В этом режиме сервис `db` и локальный том базы не создаются. Режим выбирается автоматически из JSON; дополнительных флагов Compose не требуется.

### База установлена на том же хосте, вне Docker

Используйте вариант B со следующими значениями:

```json
{
  "DATABASE_MODE": "external",
  "POSTGRES_HOST": "host.docker.internal",
  "POSTGRES_PORT": "5432"
}
```

`localhost` / `127.0.0.1` внутри контейнера указывают на сам контейнер приложения. Имя `host.docker.internal` направлено на хост Docker; для Linux в Compose добавлен `host-gateway`.

PostgreSQL на хосте должен слушать адрес, доступный из Docker, а `pg_hba.conf` и сетевой экран — разрешать роль/базу и подсеть Docker. Если PostgreSQL слушает только `127.0.0.1`, контейнер к нему не подключится. Настройки TLS выбираются по конфигурации этого PostgreSQL.

## 3. Проверить подключение и сделать копию

Проверка SQL работает в обоих режимах:

```bash
scripts/compose.sh run --rm --no-deps -T db-tools psql -X -c 'SELECT current_database(), current_user;'
```

Для резервной копии:

```bash
mkdir -p ../private/relayix-backups
chmod 700 ../private/relayix-backups
umask 077
scripts/compose.sh run --rm --no-deps -T db-tools pg_dump -Fc > "../private/relayix-backups/manual-$(date +%Y%m%d-%H%M%S).dump"
```

`db-tools` — одноразовый клиент с профилем `tools`: обычный `up -d` его не запускает. Он использует те же host/user/password/TLS, что и приложение. Пароли не нужно передавать в командной строке. Образ клиента по умолчанию — PostgreSQL 17.11; для сервера новее 17 укажите соответствующий или более новый `POSTGRES_CLIENT_IMAGE`, например `postgres:18.6-trixie` для PostgreSQL 18. `pg_dump` не поддерживает сервер старше себя по основной версии.

Для восстановления используйте `pg_restore` из того же сервиса. Перед восстановлением остановите приложение и убедитесь, что выбрана нужная целевая база. Подробности переноса существующей установки — в [UPGRADE.md](../UPGRADE.md).

## Основные переменные

| Переменная | Назначение |
| --- | --- |
| `DATABASE_MODE` | `local` или `external`; по умолчанию `local` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Адрес и порт внешней базы; порт по умолчанию `5432` |
| `POSTGRES_USER` / `POSTGRES_DB` | Роль и база; по умолчанию `relayix` |
| `POSTGRES_PASSWORD` | Пароль роли; автоматически создаётся только для новой локальной базы |
| `POSTGRES_SSLMODE` | Для внешней базы по умолчанию `verify-full`; локально используется `disable` |
| `POSTGRES_SSLROOTCERT` | Необязательный абсолютный путь к CA-сертификату на Docker-хосте |
| `POSTGRES_CLIENT_IMAGE` | Образ клиента для `psql` и резервных копий |
| `POSTGRES_IMAGE` | Образ встроенной базы; применяется только при `local` |
| `RELAYIX_DB_VOLUME` | Имя существующего локального тома; без настройки используется `<project>_db_data` |
| `RELAYIX_IMAGE` | Доступный локально или опубликованный образ приложения |
| `COMPOSE_PROJECT_NAME` | Имя установки Compose; не меняйте для существующего локального тома без переноса данных |
| `BIND_ADDRESS` / `PORT` | Адрес и порт публикации веб-интерфейса |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Первый администратор; пароль применяется при создании учётной записи |
| `ADMIN_TOKEN` | Необязательный административный токен API; генератор создаёт его автоматически |
| `COOKIE_SECURE` | `true` для доступа через HTTPS; `false` для прямого HTTP |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Нужны для Telegram MTProto/WEB; для обычного Bot API не требуются |

Нестандартное расположение единственного файла настроек выбирается так:

```bash
export RELAYIX_CONFIG_FILE=/srv/relayix-private/deployment.json
scripts/compose.sh up -d
```

## Обычные операции

```bash
scripts/compose.sh logs -f app
scripts/compose.sh restart app
scripts/compose.sh stop
scripts/compose.sh up -d
```

После изменения переменных используйте `up -d`: `restart` не обновляет окружение контейнера. Для существующего локального тома не используйте `down -v`, если хотите сохранить данные. Переключение `local` → `external` не переносит данные автоматически: сначала сделайте копию и восстановите её в выбранной внешней базе.
