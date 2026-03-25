import json
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from app.pgn_service import fetch_pgn_text, parse_pgn_winner


_GAME_ID_RE = re.compile(r"/game/(?:live|daily)/(\d+)")
_FINISHED_STATES = {"finished", "ended", "gameover", "complete", "completed", "over"}


def _extract_game_id(game_url: str) -> str:
    match = _GAME_ID_RE.search(game_url)
    if not match:
        raise ValueError("Unsupported Chess.com game URL. Expected .../game/live/<id>.")
    return match.group(1)


def _chesscom_game_url(game_id: str) -> str:
    return f"https://www.chess.com/game/live/{game_id}"


def _chesscom_callback_url(game_id: str) -> str:
    return f"https://www.chess.com/callback/live/game/{game_id}"


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; chess-status-checker/1.0)",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    payload = json.loads(content.decode(encoding, errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("Unexpected Chess.com response shape.")
    return payload


def _extract_finished_state(game_payload: dict[str, Any]) -> Optional[bool]:
    bool_keys = ("isFinished", "finished", "isGameOver", "gameOver", "over")
    for key in bool_keys:
        value = game_payload.get(key)
        if isinstance(value, bool):
            return value

    text_keys = ("status", "state", "gameStatus")
    for key in text_keys:
        value = game_payload.get(key)
        if isinstance(value, str):
            return value.strip().lower() in _FINISHED_STATES

    return None


def _extract_pgn_text(game_payload: dict[str, Any], root_payload: dict[str, Any]) -> Optional[str]:
    for container in (game_payload, root_payload):
        for key in ("pgn", "pgnText", "pgn_text"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _extract_players(game_payload: dict[str, Any], pgn_text: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    white_name = black_name = None

    white_data = game_payload.get("white")
    black_data = game_payload.get("black")

    if isinstance(white_data, dict):
        for key in ("username", "name"):
            value = white_data.get(key)
            if isinstance(value, str) and value.strip():
                white_name = value
                break

    if isinstance(black_data, dict):
        for key in ("username", "name"):
            value = black_data.get(key)
            if isinstance(value, str) and value.strip():
                black_name = value
                break

    if (white_name is None or black_name is None) and pgn_text:
        for raw_line in pgn_text.splitlines():
            line = raw_line.strip()
            if line.startswith('[White "') and line.endswith('"]'):
                white_name = line[len('[White "') : -2]
            elif line.startswith('[Black "') and line.endswith('"]'):
                black_name = line[len('[Black "') : -2]
            if white_name and black_name:
                break

    return white_name, black_name


def _players_match(
    white_name: Optional[str],
    black_name: Optional[str],
    player_a: Optional[str],
    player_b: Optional[str],
) -> Optional[bool]:
    if not player_a or not player_b:
        return None
    if not white_name or not black_name:
        return False
    actual = {white_name.casefold(), black_name.casefold()}
    expected = {player_a.casefold(), player_b.casefold()}
    return actual == expected


def check_chess_com_match_status(
    game_url: str,
    player_a: Optional[str] = None,
    player_b: Optional[str] = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    game_id = _extract_game_id(game_url)
    normalized_game_url = _chesscom_game_url(game_id)
    callback_url = _chesscom_callback_url(game_id)
    pgn_url = f"{normalized_game_url}/pgn"

    payload: dict[str, Any] = {}
    game_payload: dict[str, Any] = {}
    try:
        payload = _fetch_json(callback_url, timeout=timeout)
        raw_game_payload = payload.get("game") if isinstance(payload.get("game"), dict) else payload
        if isinstance(raw_game_payload, dict):
            game_payload = raw_game_payload
    except (urllib.error.URLError, ValueError):
        # Callback endpoint is not officially documented, so keep a PGN fallback.
        payload = {}
        game_payload = {}

    finished_by_status = _extract_finished_state(game_payload)
    pgn_text = _extract_pgn_text(game_payload, payload)

    if pgn_text is None and finished_by_status:
        pgn_text = fetch_pgn_text(pgn_url, timeout=timeout)

    if pgn_text is None and finished_by_status is None:
        with_pgn_fallback = fetch_pgn_text(pgn_url, timeout=timeout)
        if with_pgn_fallback.lstrip().startswith("["):
            pgn_text = with_pgn_fallback

    winner_color = winner_name = None
    finished_by_pgn = None
    if pgn_text:
        winner_color, winner_name = parse_pgn_winner(pgn_text)
        finished_by_pgn = winner_color in {"white", "black", "draw"}
        if winner_color == "unfinished":
            finished_by_pgn = False

    if finished_by_status is not None:
        is_finished = finished_by_status
    else:
        is_finished = bool(finished_by_pgn)

    if finished_by_status is None and pgn_text is None:
        raise ValueError("Could not determine Chess.com game status or PGN.")

    white_name, black_name = _extract_players(game_payload, pgn_text)

    return {
        "game_id": game_id,
        "game_url": normalized_game_url,
        "is_finished": is_finished,
        "winner_color": winner_color,
        "winner_name": winner_name,
        "players": {"white": white_name, "black": black_name},
        "players_match": _players_match(white_name, black_name, player_a, player_b),
        "pgn_url": pgn_url if is_finished else None,
    }
