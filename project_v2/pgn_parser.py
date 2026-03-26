import argparse
import re
import sys
import urllib.error
import urllib.request
from typing import Optional, Tuple
import time, requests


_TAG_RE = re.compile(r'^\[(\w+)\s+"(.*)"\]$')
_RESULT_RE = re.compile(r"(1-0|0-1|1/2-1/2|\*)\s*$")
SEEN = set()  # сюда кладём уже обработанные game["url"]

def _winner_from_result(
    result: Optional[str], white: Optional[str], black: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    if result == "1-0":
        return "white", white
    if result == "0-1":
        return "black", black
    if result == "1/2-1/2":
        return "draw", None
    if result == "*":
        return "unfinished", None
    return None, None


def parse_pgn_winner(pgn_text: str) -> Tuple[Optional[str], Optional[str]]:
    white = black = result = None
    movetext_lines = []

    for raw_line in pgn_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        tag_match = _TAG_RE.match(line)
        if tag_match:
            tag_name, tag_value = tag_match.group(1), tag_match.group(2)
            if tag_name == "White":
                white = tag_value
            elif tag_name == "Black":
                black = tag_value
            elif tag_name == "Result":
                result = tag_value
            continue

        movetext_lines.append(line)

    if result is None and movetext_lines:
        movetext = " ".join(movetext_lines)
        result_match = _RESULT_RE.search(movetext)
        if result_match:
            result = result_match.group(1)

    return _winner_from_result(result, white, black)


def parse_pgn_file(path: str, encoding: str = "utf-8") -> Tuple[Optional[str], Optional[str]]:
    with open(path, "r", encoding=encoding) as file:
        return parse_pgn_winner(file.read())


def fetch_pgn_text(url: str, encoding: str = "utf-8", timeout: float = 20.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        content = response.read()
        response_encoding = response.headers.get_content_charset()
        effective_encoding = response_encoding or encoding
        return content.decode(effective_encoding, errors="replace")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse PGN and print winner color and player name."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to PGN file (legacy mode).",
    )
    parser.add_argument("--file", dest="file_path", help="Path to PGN file.")
    parser.add_argument("--url", help="Download PGN from URL and parse it.")
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read PGN text from stdin.",
    )
    parser.add_argument(
        "--save-to",
        help="Save downloaded PGN to this path (works with --url).",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Text encoding for file/stdin/url fallback. Default: utf-8.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="URL download timeout in seconds. Default: 20.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    sources_selected = sum(
        bool(source)
        for source in [args.path is not None, args.file_path is not None, args.url is not None, args.stdin]
    )
    if sources_selected != 1:
        parser.error("Specify exactly one source: <path>, --file, --url, or --stdin.")

    if args.save_to and not args.url:
        parser.error("--save-to can only be used with --url.")

    try:
        if args.path or args.file_path:
            file_path = args.file_path or args.path
            winner_color, winner_name = parse_pgn_file(file_path, encoding=args.encoding)
        elif args.url:
            pgn_text = fetch_pgn_text(args.url, encoding=args.encoding, timeout=args.timeout)
            if args.save_to:
                with open(args.save_to, "w", encoding=args.encoding) as file:
                    file.write(pgn_text)
            winner_color, winner_name = parse_pgn_winner(pgn_text)
        else:
            pgn_text = sys.stdin.read()
            if not pgn_text.strip():
                print("No PGN data was received from stdin.", file=sys.stderr)
                return 1
            winner_color, winner_name = parse_pgn_winner(pgn_text)
    except (OSError, UnicodeDecodeError, urllib.error.URLError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Winner color: {winner_color}")
    print(f"Winner name: {winner_name}")
    return 0


def poll_finished_games(username: str):
    y, m = time.gmtime().tm_year, time.gmtime().tm_mon
    url = f"https://api.chess.com/pub/player/{username}/games/{y}/{m:02d}"
    games = requests.get(url, timeout=10, headers={"User-Agent":"your-app (contact@example.com)"}).json()
    for g in games.get("games", []):
        if "end_time" in g and g.get("url") not in SEEN:
            SEEN.add(g["url"])
            return g.get("pgn")  # дальше ты парсишь [Result]/[White]/[Black]
    return None

if __name__ == "__main__":
    sys.exit(main())
