import json
import urllib.error
import urllib.request
from dataclasses import dataclass


LOGIN_URL = "https://www.chess.com/login"
PLAY_URL = "https://www.chess.com/play/online"
HOME_URL = "https://www.chess.com/home"
LOGIN_AND_GO_PATH = "/login_and_go"
AUTOCOMPLETE_URL = (
    "https://www.chess.com/service/friends-search/idl/"
    "chesscom.friends_search.v1.FriendsSearchService/Autocomplete"
)


class ChessIntegrationError(Exception):
    pass


@dataclass
class ChessIntegrationResult:
    chess_username: str
    chess_uuid: str
    chess_cookie_header: str
    chess_csrf_token: str


def _attach_user_id_detector(page, holder: dict) -> None:
    def on_request(request):
        if request.method != "POST":
            return
        if "DispatchEventBatch" not in request.url:
            return
        user_id = _extract_user_id_from_activity_post(request.post_data or "")
        if user_id:
            holder["detected_user_uuid"] = user_id

    page.on("request", on_request)


def _extract_user_id_from_activity_post(raw_post_data: str) -> str | None:
    if not raw_post_data:
        return None
    try:
        payload = json.loads(raw_post_data)
    except json.JSONDecodeError:
        return None

    for key in ("typedEvents", "trackEvents", "navigationEvents"):
        events = payload.get(key)
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            headers = event.get("headers")
            if not isinstance(headers, dict):
                continue
            user_id = headers.get("userId")
            if isinstance(user_id, str) and user_id.strip():
                return user_id.strip()
    return None


def _build_cookie_header(cookies: list[dict]) -> str:
    pairs = []
    seen = set()
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        if name in seen:
            continue
        seen.add(name)
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _extract_csrf_token(cookies: list[dict]) -> str:
    for cookie in cookies:
        if cookie.get("name") == "csrftoken" and cookie.get("value"):
            return str(cookie["value"])
    return ""


def _ensure_authenticated_session(cookie_header: str, timeout: float) -> None:
    request = urllib.request.Request(
        HOME_URL,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0",
            "Cookie": cookie_header,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = (response.geturl() or "").strip().lower()
    except urllib.error.URLError as error:
        raise ChessIntegrationError(f"Chess session validation network error: {error}") from error

    if LOGIN_AND_GO_PATH in final_url:
        raise ChessIntegrationError(
            "Chess.com session is not authenticated. "
            "Please sign in on Chess.com and reconnect your profile."
        )


def _fetch_uuid_by_username(chess_username: str, cookie_header: str, csrf_token: str, timeout: float) -> str:
    payload = {
        "prefix": chess_username,
        "includeFriends": True,
        "includeSuggestions": True,
        "friendsLimit": 6,
        "suggestionsLimit": 6,
        "exactUsernameFirst": True,
        "boostUsername": True,
    }
    data = json.dumps(payload).encode("utf-8")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.chess.com",
        "Referer": PLAY_URL,
        "User-Agent": "Mozilla/5.0",
        "Cookie": cookie_header,
    }
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    request = urllib.request.Request(
        AUTOCOMPLETE_URL,
        data=data,
        method="POST",
        headers=headers,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise ChessIntegrationError(f"Chess username lookup failed: HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise ChessIntegrationError(f"Chess username lookup network error: {error}") from error

    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as error:
        raise ChessIntegrationError("Chess username lookup returned invalid JSON.") from error

    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        suggestions = []

    target = chess_username.casefold()
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        user_view = item.get("userView") if isinstance(item.get("userView"), dict) else {}
        found_username = (user_view.get("username") or "").strip()
        found_uuid = (item.get("uuid") or user_view.get("id") or "").strip()
        if found_username.casefold() == target and found_uuid:
            return found_uuid

    raise ChessIntegrationError(
        "Could not detect chess_uuid for this username. "
        "Make sure the username exists and you are logged in to the same Chess.com account."
    )


def collect_chess_credentials(
    *,
    chess_username: str,
    chess_password: str,
    timeout_ms: int = 45000,
) -> ChessIntegrationResult:
    chess_username = (chess_username or "").strip()
    chess_password = chess_password or ""
    if not chess_username:
        raise ChessIntegrationError("Chess username is required.")
    if not chess_password:
        raise ChessIntegrationError("Chess password is required.")

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
    except ImportError as error:
        raise ChessIntegrationError(
            "Playwright is not installed. Install it and browser runtime first."
        ) from error

    detected = {"detected_user_uuid": None}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        _attach_user_id_detector(page, detected)

        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.locator("input#login-username").fill(chess_username)
            page.locator("input#login-password").fill(chess_password)
            page.locator("button[type='submit']").click()
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

            page.goto(PLAY_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2500)
        except PlaywrightTimeoutError as error:
            browser.close()
            raise ChessIntegrationError(
                "Chess.com integration timed out. Check internet and account login details."
            ) from error
        except Exception as error:
            browser.close()
            raise ChessIntegrationError(f"Chess.com integration failed: {error}") from error

        cookies = page.context.cookies("https://www.chess.com")
        browser.close()

    if not cookies:
        raise ChessIntegrationError("Could not read Chess.com cookies after login.")

    cookie_header = _build_cookie_header(cookies)
    csrf_token = _extract_csrf_token(cookies)
    request_timeout = max(10.0, timeout_ms / 1000.0)

    _ensure_authenticated_session(cookie_header, timeout=request_timeout)

    username_uuid = _fetch_uuid_by_username(
        chess_username=chess_username,
        cookie_header=cookie_header,
        csrf_token=csrf_token,
        timeout=request_timeout,
    )

    if detected["detected_user_uuid"] and username_uuid != detected["detected_user_uuid"]:
        raise ChessIntegrationError(
            "You logged in to one Chess.com account but entered another username. "
            "Use matching username/password."
        )

    return ChessIntegrationResult(
        chess_username=chess_username.lower(),
        chess_uuid=username_uuid,
        chess_cookie_header=cookie_header,
        chess_csrf_token=csrf_token,
    )


def collect_chess_credentials_interactive(
    *,
    chess_username: str,
    timeout_ms: int = 240000,
) -> ChessIntegrationResult:
    chess_username = (chess_username or "").strip()
    if not chess_username:
        raise ChessIntegrationError("Chess username is required.")

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
    except ImportError as error:
        raise ChessIntegrationError(
            "Playwright is not installed. Install it and browser runtime first."
        ) from error

    detected = {"detected_user_uuid": None}

    with sync_playwright() as playwright:
        try:
            try:
                # Prefer installed Google Chrome for interactive OAuth flows.
                browser = playwright.chromium.launch(headless=False, channel="chrome")
            except Exception:
                browser = playwright.chromium.launch(headless=False)
        except Exception as error:
            raise ChessIntegrationError(
                "Could not open browser window for interactive login. "
                "Run this on a machine with GUI access."
            ) from error

        page = browser.new_page()
        _attach_user_id_detector(page, detected)

        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            # User logs in manually (Google, 2FA, captcha) in the opened browser.
            page.wait_for_url("**/play/online**", timeout=timeout_ms)
            page.wait_for_timeout(3000)
            page.goto(PLAY_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError as error:
            browser.close()
            raise ChessIntegrationError(
                "Interactive login timed out. Complete Chess.com login and open Play Online page."
            ) from error
        except Exception as error:
            browser.close()
            raise ChessIntegrationError(f"Interactive login failed: {error}") from error

        cookies = page.context.cookies("https://www.chess.com")
        browser.close()

    if not cookies:
        raise ChessIntegrationError("Could not read Chess.com cookies after interactive login.")

    cookie_header = _build_cookie_header(cookies)
    csrf_token = _extract_csrf_token(cookies)
    request_timeout = max(10.0, timeout_ms / 1000.0)

    _ensure_authenticated_session(cookie_header, timeout=request_timeout)

    username_uuid = _fetch_uuid_by_username(
        chess_username=chess_username,
        cookie_header=cookie_header,
        csrf_token=csrf_token,
        timeout=request_timeout,
    )

    if detected["detected_user_uuid"] and username_uuid != detected["detected_user_uuid"]:
        raise ChessIntegrationError(
            "Logged-in Chess.com account does not match entered username."
        )

    return ChessIntegrationResult(
        chess_username=chess_username.lower(),
        chess_uuid=username_uuid,
        chess_cookie_header=cookie_header,
        chess_csrf_token=csrf_token,
    )
