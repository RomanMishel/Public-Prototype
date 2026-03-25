import re
import urllib.request
from pathlib import Path
from typing import Optional, Tuple


_TAG_RE = re.compile(r'^\[(\w+)\s+"(.*)"\]$')
_RESULT_RE = re.compile(r"(1-0|0-1|1/2-1/2|\*)\s*$")


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
    return parse_pgn_winner(Path(path).read_text(encoding=encoding))


def fetch_pgn_text(url: str, encoding: str = "utf-8", timeout: float = 20.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        content = response.read()
        response_encoding = response.headers.get_content_charset()
        effective_encoding = response_encoding or encoding
        return content.decode(effective_encoding, errors="replace")

