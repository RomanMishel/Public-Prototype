# Security Best Practices Report: Whole Project (`B_S_`)

## Executive Summary
Проведен статический security-аудит всего проекта (Python/FastAPI/Django/automation scripts + infra файлы). Обнаружены критичные и высокие риски: неаутентифицированная запись файлов в FastAPI, утечка секретов в репозитории, отсутствие объектной авторизации в Django-операциях лобби и хранение паролей через MD5 в legacy-коде.

Общий риск: **High**.

## Scope
- Root scripts: `chess_sniffer.py`, `subagent_lobby_v2.py`, `subagent_lobby_check.py`, `winner_listener.py`, `pgn_parser.py`, `run_pgn_job.ps1`
- `project_v2` (Django + FastAPI)
- `project_v1` (legacy Django/scripts)
- Config and runtime files: `.env`, `docker-compose.yml`, log files

## Findings

### SEC-001 — Critical — Arbitrary file write in FastAPI endpoint (`/pgn/parse`)
- Location: `project_v2/app/main.py:72-74`, route `project_v2/app/main.py:130-134`
- Evidence:
  - `if payload.save_to: await asyncio.to_thread(Path(payload.save_to).write_text, pgn_text, payload.encoding)`
  - Endpoint is publicly exposed without auth dependency.
- Impact: удаленный пользователь может записывать произвольные файлы на сервере от имени процесса (DoS, подмена кода/конфигов, потенциальная эскалация до RCE при небезопасной эксплуатации).
- Fix:
  - Удалить `save_to` из публичного API или разрешить только server-side fixed directory + strict allowlist.
  - Запретить абсолютные пути и `..`.
  - Добавить аутентификацию/авторизацию на endpoint.

### SEC-002 — High — SSRF via untrusted `pgn_url`
- Location: `project_v2/app/main.py:69-71`
- Evidence: `fetch_pgn_text(payload.pgn_url, ...)` вызывается напрямую из пользовательского payload.
- Impact: сервис может обращаться к внутренним ресурсам (`localhost`, приватные подсети, metadata endpoints), что часто ведет к утечке инфраструктурных данных.
- Fix:
  - Разрешать только `https` и только allowlist доменов.
  - Блокировать приватные IP/localhost/link-local.
  - Ограничить редиректы и таймауты.

### SEC-003 — High — Broken object-level authorization in lobby finish
- Location: `project_v2/auth_system/views.py:220-238`
- Evidence: любой `@login_required` пользователь может выполнить `finish_lobby` по `lobby_id`; отсутствует проверка, что пользователь является host/guest/staff.
- Impact: любой авторизованный пользователь может завершать чужие матчи и менять результат/URL.
- Fix:
  - Проверять, что `request.user` связан с `lobby_obj.host` или `lobby_obj.guest` (или `is_staff`).
  - Для остальных возвращать `403`.

### SEC-004 — High — Secrets committed to repository (`.env` tracked by git)
- Location: `.env:1-7` and git index (`git ls-files .env` показывает, что файл отслеживается)
- Evidence:
  - `PLATFORM_PASSWORD=pass12345`
  - `CHESS_LOGIN=...`
  - `CHESS_PASSWORD=...`
- Impact: компрометация учетных данных при любом доступе к репозиторию/бэкапам.
- Fix:
  - Немедленно ротировать все скомпрометированные креды.
  - Удалить `.env` из git history/индекса и хранить только `.env.example`.

### SEC-005 — High — Insecure Django production defaults (hardcoded key + debug)
- Location: `project_v2/project_v2/settings.py:11`, `project_v2/project_v2/settings.py:14`
- Evidence:
  - Hardcoded `SECRET_KEY`
  - `DEBUG = True`
- Impact: при production-развертывании возможна утечка чувствительных данных через debug pages; hardcoded key упрощает злоупотребления подписью cookie/token-like данных.
- Fix:
  - Загружать `SECRET_KEY` из env/secrets manager.
  - `DEBUG=False` вне dev.
  - Добавить production security settings (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, и т.д. по TLS-среде).

### SEC-006 — High — Weak password hashing (MD5) in legacy auth code
- Location: `project_v1/registration/registration.py:37`, `project_v1/registration/login.py:10`
- Evidence: `hashlib.md5(...).hexdigest()`
- Impact: MD5 быстро перебирается; при утечке базы пароли легко восстанавливаются.
- Fix:
  - Для web-auth использовать стандартные Django hashers (`set_password/check_password`) или Argon2/bcrypt в non-Django flows.

### SEC-007 — Medium — Browser sandbox protections disabled in automation
- Location: `subagent_lobby_v2.py:421-424`
- Evidence:
  - `--no-sandbox`
  - `--disable-features=IsolateOrigins,site-per-process`
- Impact: снижение изоляции браузера увеличивает ущерб при эксплуатации browser/renderer уязвимостей.
- Fix:
  - Удалить эти флаги, если нет крайней необходимости.
  - Запускать в наименее привилегированном окружении.

### SEC-008 — Medium — Sensitive network data logging (possible token/session leak)
- Location: `chess_sniffer.py:80`, `chess_sniffer.py:92`, `chess_sniffer.py:107-108`
- Evidence: в лог пишутся request/response payload и WebSocket frames.
- Impact: логи могут содержать токены/идентификаторы сессии/персональные данные.
- Fix:
  - Redact (`token`, `authorization`, `cookie`, `session`), ограничить payload logging, включать deep logging только в debug mode.
  - Ввести ротацию и права доступа к логам.

### SEC-009 — Medium — Insecure default DB credentials + exposed DB port
- Location: `project_v2/docker-compose.yml:13`, `project_v2/docker-compose.yml:20-24`
- Evidence:
  - `postgres:postgres` credentials
  - `5432:5432` exposed
- Impact: при доступности хоста в сети риск несанкционированного доступа к БД.
- Fix:
  - Секреты в env/secret manager.
  - Не публиковать 5432 наружу без необходимости.

### SEC-010 — Medium — Dev-mode server flags in compose runtime
- Location: `project_v2/docker-compose.yml:8`
- Evidence: `uvicorn ... --reload`
- Impact: не production-hardening режим; повышенный риск нестабильности/непредсказуемого поведения в проде.
- Fix:
  - Для production убирать `--reload`, использовать production ASGI setup.

### SEC-011 — Low — Logout uses GET (CSRF-able logout)
- Location: `project_v2/auth_system/views.py:70-72`, `project_v2/auth_system/templates/profile.html:10`
- Evidence: logout endpoint без ограничения метода и вызывается `<a href=...>`.
- Impact: сторонний сайт может принудительно разлогинить пользователя.
- Fix:
  - Перевести logout на `POST` + CSRF token.

### SEC-012 — Low — Runtime logs tracked in git
- Location: `project_v2/runserver_err.log`, `project_v2/runserver_error.log`, `project_v2/runserver_out.log` (tracked)
- Evidence: `git ls-files` показывает эти логи в репозитории.
- Impact: информационные утечки (пути, stack traces, operational details).
- Fix:
  - Исключить runtime logs из VCS, очистить их из индекса.

## Positive Notes
- В Django-шаблонах `project_v2` state-changing формы используют `{% csrf_token %}`.
- В `project_v2/auth_system/models.py` есть server-side model validation (`full_clean()` в `save()`).
- В `chess_sniffer.py` добавлена обработка ошибок запуска и timeout при `goto`.

## Priority Fix Order
1. SEC-001 (arbitrary file write) + SEC-002 (SSRF) в FastAPI.
2. SEC-004 (утечка секретов, ротация + удаление из git).
3. SEC-003 (IDOR в `finish_lobby`).
4. SEC-005 (Django production hardening: secret/debug/cookies/security settings).
5. SEC-006 (замена MD5 в legacy auth).
6. SEC-007/SEC-008/SEC-009/SEC-010 (hardening automation/infra/logging).
