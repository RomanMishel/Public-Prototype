import json
import urllib.error
import urllib.request

BASE_URL = "https://www.chess.com"


class ChessComClientError(Exception):
    pass


def _request_json(actor, method: str, path: str, payload: dict | None = None, timeout: float = 20.0) -> dict:
    if not actor.chess_cookie_header:
        raise ChessComClientError(f"Chess credentials are missing for user {actor.chess_username}")

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.chess.com",
        "Referer": "https://www.chess.com/play/online",
        "User-Agent": "Mozilla/5.0",
        "Cookie": actor.chess_cookie_header,
    }
    if actor.chess_csrf_token:
        headers["X-CSRF-Token"] = actor.chess_csrf_token

    req = urllib.request.Request(
        url=f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ChessComClientError(f"Chess API HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise ChessComClientError(f"Chess API network error: {e}") from e


def send_challenge(
    actor,
    to_user_uuid: str,
    base_seconds: int = 600,
    increment_seconds: int = 0,
    rated: bool = True,
) -> dict:
    payload = {
        "capabilities": ["rated"] if rated else [],
        "rated": rated,
        "gameType": "chess",
        "timeControl": {"base": f"PT{base_seconds}S", "increment": f"PT{increment_seconds}S"},
        "toUserId": to_user_uuid,
        "ratingRange": {"upper": None, "lower": None},
    }
    return _request_json(actor, "POST", "/service/matcher/challenges/chess", payload)


def accept_challenge(actor, challenge_id: str) -> dict:
    payload = {"capabilities": ["rated"]}
    return _request_json(actor, "POST", f"/service/matcher/challenges/{challenge_id}/accept", payload)
