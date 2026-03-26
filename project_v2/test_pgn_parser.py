import io
import tempfile
import time
import unittest
from unittest.mock import patch

import pgn_parser


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


class FakeRequestsResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class ParsePgnWinnerTests(unittest.TestCase):
    def test_parses_white_win_from_tags(self):
        pgn = "\n".join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                '[Result "1-0"]',
                "",
                "1. e4 e5 2. Nf3 Nc6",
            ]
        )
        self.assertEqual(pgn_parser.parse_pgn_winner(pgn), ("white", "Alice"))

    def test_parses_black_win_from_tags(self):
        pgn = "\n".join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                '[Result "0-1"]',
                "",
                "1. d4 d5 2. c4",
            ]
        )
        self.assertEqual(pgn_parser.parse_pgn_winner(pgn), ("black", "Bob"))

    def test_falls_back_to_movetext_result(self):
        pgn = "\n".join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                "",
                "1. e4 e5 2. Nf3 Nc6 1/2-1/2",
            ]
        )
        self.assertEqual(pgn_parser.parse_pgn_winner(pgn), ("draw", None))

    def test_parses_unfinished_game(self):
        pgn = "\n".join(
            [
                '[White "Alice"]',
                '[Black "Bob"]',
                '[Result "*"]',
                "",
                "1. e4 c5",
            ]
        )
        self.assertEqual(pgn_parser.parse_pgn_winner(pgn), ("unfinished", None))


class ParsePgnFileTests(unittest.TestCase):
    def test_parse_pgn_file_reads_and_parses_file(self):
        pgn = "\n".join(['[White "Alice"]', '[Black "Bob"]', '[Result "1-0"]'])
        with tempfile.NamedTemporaryFile("w", suffix=".pgn", delete=False, encoding="utf-8") as tmp:
            tmp.write(pgn)
            path = tmp.name

        self.assertEqual(pgn_parser.parse_pgn_file(path), ("white", "Alice"))


class FetchPgnTextTests(unittest.TestCase):
    @patch("pgn_parser.urllib.request.urlopen")
    def test_uses_response_header_encoding_when_available(self, mocked_urlopen):
        expected = "test-\u20ac"
        mocked_urlopen.return_value = FakeResponse(expected.encode("utf-8"), charset="utf-8")

        text = pgn_parser.fetch_pgn_text("https://example.test/file.pgn", encoding="cp1251")

        self.assertEqual(text, expected)

    @patch("pgn_parser.urllib.request.urlopen")
    def test_uses_fallback_encoding_when_header_missing(self, mocked_urlopen):
        expected = "\u0442\u0435\u0441\u0442"
        mocked_urlopen.return_value = FakeResponse(expected.encode("cp1251"), charset=None)

        text = pgn_parser.fetch_pgn_text("https://example.test/file.pgn", encoding="cp1251")

        self.assertEqual(text, expected)


class MainTests(unittest.TestCase):
    def test_main_reads_from_stdin(self):
        stdin = io.StringIO('\n'.join(['[White "Alice"]', '[Black "Bob"]', '[Result "1-0"]']))
        stdout = io.StringIO()

        with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
            exit_code = pgn_parser.main(["--stdin"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Winner color: white", output)
        self.assertIn("Winner name: Alice", output)

    def test_main_returns_error_for_empty_stdin(self):
        stdin = io.StringIO("")
        stderr = io.StringIO()

        with patch("sys.stdin", stdin), patch("sys.stderr", stderr):
            exit_code = pgn_parser.main(["--stdin"])

        self.assertEqual(exit_code, 1)
        self.assertIn("No PGN data was received from stdin.", stderr.getvalue())

    @patch("pgn_parser.fetch_pgn_text")
    def test_main_downloads_and_saves_from_url(self, mocked_fetch_pgn_text):
        pgn_text = "\n".join(['[White "Alice"]', '[Black "Bob"]', '[Result "0-1"]'])
        mocked_fetch_pgn_text.return_value = pgn_text
        stdout = io.StringIO()

        with tempfile.NamedTemporaryFile("r", suffix=".pgn", delete=False, encoding="utf-8") as tmp:
            save_path = tmp.name

        with patch("sys.stdout", stdout):
            exit_code = pgn_parser.main(
                ["--url", "https://example.test/file.pgn", "--save-to", save_path]
            )

        self.assertEqual(exit_code, 0)
        mocked_fetch_pgn_text.assert_called_once_with(
            "https://example.test/file.pgn", encoding="utf-8", timeout=20.0
        )
        self.assertIn("Winner color: black", stdout.getvalue())
        with open(save_path, "r", encoding="utf-8") as file:
            self.assertEqual(file.read(), pgn_text)


class PollFinishedGamesTests(unittest.TestCase):
    def setUp(self):
        pgn_parser.SEEN.clear()

    def test_returns_first_finished_unseen_game_pgn(self):
        fake_time = time.struct_time((2026, 2, 15, 0, 0, 0, 0, 46, 0))
        payload = {
            "games": [
                {"url": "https://www.chess.com/game/live/1"},
                {
                    "url": "https://www.chess.com/game/live/2",
                    "end_time": 1700000000,
                    "pgn": '[White "A"]\n[Black "B"]\n[Result "1-0"]',
                },
            ]
        }

        with patch("pgn_parser.time.gmtime", return_value=fake_time), patch(
            "pgn_parser.requests.get", return_value=FakeRequestsResponse(payload)
        ) as mocked_get:
            pgn = pgn_parser.poll_finished_games("sample-user")

        self.assertEqual(pgn, '[White "A"]\n[Black "B"]\n[Result "1-0"]')
        self.assertIn("https://www.chess.com/game/live/2", pgn_parser.SEEN)
        mocked_get.assert_called_once_with(
            "https://api.chess.com/pub/player/sample-user/games/2026/02",
            timeout=10,
            headers={"User-Agent": "your-app (contact@example.com)"},
        )

    def test_returns_none_when_game_already_seen(self):
        seen_url = "https://www.chess.com/game/live/3"
        pgn_parser.SEEN.add(seen_url)
        payload = {"games": [{"url": seen_url, "end_time": 1700000001, "pgn": "PGN"}]}

        with patch("pgn_parser.requests.get", return_value=FakeRequestsResponse(payload)):
            result = pgn_parser.poll_finished_games("sample-user")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
