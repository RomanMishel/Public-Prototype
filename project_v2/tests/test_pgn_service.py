import tempfile
import unittest
from unittest.mock import patch

from app.pgn_service import fetch_pgn_text, parse_pgn_file, parse_pgn_winner


class FakeHeaders:
    def __init__(self, charset=None):
        self._charset = charset

    def get_content_charset(self):
        return self._charset


class FakeResponse:
    def __init__(self, data: bytes, charset=None):
        self._data = data
        self.headers = FakeHeaders(charset=charset)

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class ParsePgnWinnerTests(unittest.TestCase):
    def test_parses_white_win_from_tags(self):
        pgn = '\n'.join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                '[Result "1-0"]',
                '',
                '1. e4 e5 2. Nf3 Nc6',
            ]
        )
        self.assertEqual(parse_pgn_winner(pgn), ("white", "Alice"))

    def test_parses_black_win_from_tags(self):
        pgn = '\n'.join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                '[Result "0-1"]',
                '',
                '1. d4 d5 2. c4',
            ]
        )
        self.assertEqual(parse_pgn_winner(pgn), ("black", "Bob"))

    def test_falls_back_to_movetext_result(self):
        pgn = '\n'.join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                '',
                '1. e4 e5 2. Nf3 Nc6 1/2-1/2',
            ]
        )
        self.assertEqual(parse_pgn_winner(pgn), ("draw", None))

    def test_parses_unfinished_game(self):
        pgn = '\n'.join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                '[Result "*"]',
                '',
                '1. e4 c5',
            ]
        )
        self.assertEqual(parse_pgn_winner(pgn), ("unfinished", None))

    def test_returns_none_for_unknown_result(self):
        pgn = '\n'.join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                '',
                '1. e4 e5',
            ]
        )
        self.assertEqual(parse_pgn_winner(pgn), (None, None))


class ParsePgnFileTests(unittest.TestCase):
    def test_parse_pgn_file_reads_and_parses_file(self):
        pgn = '\n'.join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                '[Result "1-0"]',
            ]
        )
        with tempfile.NamedTemporaryFile("w", suffix=".pgn", delete=False, encoding="utf-8") as tmp:
            tmp.write(pgn)
            path = tmp.name

        self.assertEqual(parse_pgn_file(path), ("white", "Alice"))


class FetchPgnTextTests(unittest.TestCase):
    @patch("app.pgn_service.urllib.request.urlopen")
    def test_uses_response_header_encoding_when_available(self, mocked_urlopen):
        expected = "test-\u20ac"
        mocked_urlopen.return_value = FakeResponse(expected.encode("utf-8"), charset="utf-8")

        text = fetch_pgn_text("https://example.test/file.pgn", encoding="cp1251")

        self.assertEqual(text, expected)

    @patch("app.pgn_service.urllib.request.urlopen")
    def test_uses_fallback_encoding_when_header_missing(self, mocked_urlopen):
        expected = "\u0442\u0435\u0441\u0442"
        mocked_urlopen.return_value = FakeResponse(expected.encode("cp1251"), charset=None)

        text = fetch_pgn_text("https://example.test/file.pgn", encoding="cp1251")

        self.assertEqual(text, expected)


if __name__ == "__main__":
    unittest.main()
