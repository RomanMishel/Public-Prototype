import asyncio
import contextlib
import logging
import os
import urllib.error
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.check_match_status import check_chess_com_match_status
from app.pgn_service import fetch_pgn_text, parse_pgn_file, parse_pgn_winner

app = FastAPI()
logger = logging.getLogger(__name__)


class PgnParseRequest(BaseModel):
    pgn_text: Optional[str] = None
    pgn_url: Optional[str] = None
    pgn_file_path: Optional[str] = None
    save_to: Optional[str] = None
    encoding: str = "utf-8"
    timeout: float = 20.0


class PgnParseResponse(BaseModel):
    winner_color: Optional[str]
    winner_name: Optional[str]


class ChessComMatchStatusRequest(BaseModel):
    game_url: str
    player_a: Optional[str] = None
    player_b: Optional[str] = None
    timeout: float = 20.0


class ChessComMatchStatusResponse(BaseModel):
    game_id: str
    game_url: str
    is_finished: bool
    winner_color: Optional[str]
    winner_name: Optional[str]
    players: dict[str, Optional[str]]
    players_match: Optional[bool]
    pgn_url: Optional[str]


async def _parse_from_request(payload: PgnParseRequest) -> dict:
    sources_selected = sum(
        bool(source) for source in [payload.pgn_text, payload.pgn_url, payload.pgn_file_path]
    )
    if sources_selected != 1:
        raise HTTPException(
            status_code=400,
            detail="Specify exactly one source: pgn_text, pgn_url, or pgn_file_path.",
        )

    try:
        if payload.pgn_text:
            winner_color, winner_name = parse_pgn_winner(payload.pgn_text)
        elif payload.pgn_file_path:
            winner_color, winner_name = await asyncio.to_thread(
                parse_pgn_file, payload.pgn_file_path, payload.encoding
            )
        else:
            pgn_text = await asyncio.to_thread(
                fetch_pgn_text, payload.pgn_url, payload.encoding, payload.timeout
            )
            if payload.save_to:
                await asyncio.to_thread(Path(payload.save_to).write_text, pgn_text, payload.encoding)
            winner_color, winner_name = parse_pgn_winner(pgn_text)
    except (OSError, UnicodeDecodeError, urllib.error.URLError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {"winner_color": winner_color, "winner_name": winner_name}


async def _poll_pgn_source() -> None:
    url = os.getenv("PGN_SOURCE_URL")
    if not url:
        return

    interval = float(os.getenv("PGN_POLL_INTERVAL_SEC", "60"))
    timeout = float(os.getenv("PGN_HTTP_TIMEOUT_SEC", "20"))
    encoding = os.getenv("PGN_TEXT_ENCODING", "utf-8")
    save_to = os.getenv("PGN_SAVE_TO")

    while True:
        try:
            pgn_text = await asyncio.to_thread(fetch_pgn_text, url, encoding, timeout)
            if save_to:
                await asyncio.to_thread(Path(save_to).write_text, pgn_text, encoding)
            winner_color, winner_name = parse_pgn_winner(pgn_text)
            app.state.latest_pgn_result = {
                "winner_color": winner_color,
                "winner_name": winner_name,
            }
            logger.info("PGN polled: winner_color=%s winner_name=%s", winner_color, winner_name)
        except Exception:
            logger.exception("PGN polling failed.")

        await asyncio.sleep(interval)


@app.on_event("startup")
async def on_startup() -> None:
    app.state.latest_pgn_result = None
    app.state.pgn_poller_task = None

    if os.getenv("PGN_SOURCE_URL"):
        app.state.pgn_poller_task = asyncio.create_task(_poll_pgn_source())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task = getattr(app.state, "pgn_poller_task", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/pgn/parse", response_model=PgnParseResponse)
async def parse_pgn(payload: PgnParseRequest):
    result = await _parse_from_request(payload)
    app.state.latest_pgn_result = result
    return result


@app.get("/pgn/latest", response_model=Optional[PgnParseResponse])
def latest_pgn_result():
    return app.state.latest_pgn_result


@app.post("/chesscom/match-status", response_model=ChessComMatchStatusResponse)
async def chesscom_match_status(payload: ChessComMatchStatusRequest):
    try:
        return await asyncio.to_thread(
            check_chess_com_match_status,
            payload.game_url,
            payload.player_a,
            payload.player_b,
            payload.timeout,
        )
    except (ValueError, urllib.error.URLError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
