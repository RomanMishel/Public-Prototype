# Chess Lobby Prototype

This repository contains a prototype platform where two users can:

- register and log in;
- create and accept a chess lobby;
- link a Chess.com profile;
- move from the platform flow to Chess.com play flow.

The project is a prototype and is still in active development.

## Current Status

What currently works:

- Django-based user registration and login;
- lobby creation and lobby acceptance;
- basic Chess.com profile linking flow;
- FastAPI utilities for PGN parsing and match status checks;
- automated tests for the main lobby flow and PGN parsing.

What is still experimental:

- deep Chess.com integration that would automatically place both users into the same shared game;
- browser-driven authentication flows, because they depend on third-party behavior outside this codebase.

## Product Goal

The goal of this prototype is simple:

- user A creates a lobby;
- user B accepts the lobby;
- both users continue into the same Chess.com play flow as smoothly as possible.

This public repository focuses on the lobby and coordination part of that experience.

## Tech Stack

- Python
- Django
- django-allauth
- FastAPI
- Playwright
- SQLite for local development

## Project Structure

- `auth_system/` - Django app for accounts, lobbies, and Chess.com integration logic
- `project_v2/` - Django project configuration
- `app/` - FastAPI utilities for PGN and match status helpers
- `tests/` - unit tests for PGN parsing

## What To Review First

If you are opening this repository for a quick review, start here:

- `project_v2/auth_system/views.py`
- `project_v2/auth_system/models.py`
- `project_v2/auth_system/templates/lobby.html`
- `project_v2/auth_system/chess_integration.py`

These files show the core lobby flow and current Chess.com integration direction.

## Local Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Install Playwright browser runtime:

```bash
playwright install
```

4. Run Django:

```bash
python manage.py runserver
```

5. Run FastAPI utilities:

```bash
uvicorn app.main:app --reload
```

## Tests

Run Django tests:

```bash
python manage.py test
```

Run PGN tests:

```bash
python -m unittest tests.test_pgn_service -v
```

## Notes

- Local development uses `db.sqlite3`, which is not intended for publication.
- Browser automation and third-party login behavior may change outside the control of this repository.
- This repository is meant to demonstrate the project structure, current implementation, and direction of the platform.
- Secrets, personal data, and local runtime files are intentionally excluded from this public prototype.
