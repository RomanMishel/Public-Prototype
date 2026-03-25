import re

import logging

from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from .chess_integration import (
    ChessIntegrationError,
    collect_chess_credentials,
    collect_chess_credentials_interactive,
)
from .models import ChessPlayer, GameLobby

logger = logging.getLogger(__name__)


def register(request):
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        email = (request.POST.get("email") or "").strip()
        if not username or not password:
            return render(
                request,
                "register.html",
                {"error": "Username and password are required."},
            )
        if not re.fullmatch(r"[A-Za-z]+", username):
            return render(
                request,
                "register.html",
                {"error": "Username must contain only Latin letters (A-Z)."},
            )
        if User.objects.filter(username__iexact=username).exists():
            return render(
                request,
                "register.html",
                {"error": "Username already exists."},
            )
        if email and User.objects.filter(email__iexact=email).exists():
            return render(
                request,
                "register.html",
                {"error": "Email already exists."},
            )
        username_normalized = username.lower()
        User.objects.create_user(username=username_normalized, password=password, email=email)
        return redirect("login")
    return render(request, "register.html")


def login(request):
    if request.method == "POST":
        login_value = (request.POST.get("login") or request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=login_value, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect("profile")
        return render(
            request,
            "login.html",
            {"error": "Invalid credentials."},
        )
    return render(request, "login.html")


def logout(request):
    auth_logout(request)
    return redirect("login")


@login_required
def profile(request):
    player = _get_or_create_chess_player_for_user(request.user)
    is_connected = bool(
        player.chess_uuid and player.chess_cookie_header
    )
    return render(
        request,
        "profile.html",
        {
            "chess_player": player,
            "chess_connected": is_connected,
            "chess_connected_now": request.GET.get("chess_connected") == "1",
        },
    )


def _get_or_create_chess_player_for_user(user: User) -> ChessPlayer:
    username = (user.username or "").strip().lower()
    player = ChessPlayer.objects.filter(user=user).first()
    if player:
        return player

    player_by_username = ChessPlayer.objects.filter(chess_username=username).first()
    if player_by_username:
        if player_by_username.user_id is None:
            player_by_username.user = user
            player_by_username.save(update_fields=["user"])
        return player_by_username

    return ChessPlayer.objects.create(
        user=user,
        chess_username=username,
        chess_profile_url=f"https://www.chess.com/member/{username}",
    )


def _render_lobby_page(request, *, error: str | None = None):
    current_player = _get_or_create_chess_player_for_user(request.user)
    open_lobbies = (
        GameLobby.objects.select_related("host")
        .filter(status=GameLobby.Status.INVITED, guest__isnull=True)
        .exclude(host=current_player)
    )
    my_lobbies = (
    GameLobby.objects.select_related("host", "guest", "winner")
    .filter(Q(host=current_player) | Q(guest=current_player))
    .order_by("-created_at")[:10]
    )
    my_open_lobbies_count = GameLobby.objects.filter(
        status=GameLobby.Status.INVITED,
        guest__isnull=True,
        host=current_player,
    ).count()

    context = {
    "open_lobbies": open_lobbies,
    "my_lobbies": my_lobbies,
    "my_open_lobbies_count": my_open_lobbies_count,
    "current_player_id": current_player.id,
    }

    if error:
        context["error"] = error
    return render(request, "lobby.html", context)


@login_required
def lobby(request):
    return _render_lobby_page(request)


# @login_required
# def seed_default_players(request):
#     if request.method != "POST":
#         return redirect("lobby")

#     for username, url in DEFAULT_CHESS_PLAYERS:
#         ChessPlayer.objects.update_or_create(
#             chess_username=username.lower(),
#             defaults={"chess_profile_url": url},
#         )

#     return redirect("lobby")


@login_required
def create_lobby(request):
    if request.method == "GET":
        return render(
            request,
            "create_lobby.html",
            {"selected_game": GameLobby.GameType.CHESS},
        )

    if request.method != "POST":
        return redirect("lobby")

    game_type = (request.POST.get("game_type") or "").strip().lower()
    valid_game_types = {choice for choice, _ in GameLobby.GameType.choices}

    if game_type not in valid_game_types:
        return render(
            request,
            "create_lobby.html",
            {
                "error": "Select a valid game.",
                "selected_game": GameLobby.GameType.CHESS,
            },
        )

    host = _get_or_create_chess_player_for_user(request.user)
    GameLobby.objects.create(
        host=host,
        guest=None,
        status=GameLobby.Status.INVITED,
        game_type=game_type,
    )
    return redirect("lobby")


@login_required
def connect_chess_account(request):
    default_username = (request.user.username or "").strip().lower()
    if request.method == "GET":
        return render(
            request,
            "connect_chess.html",
            {
                "chess_username": default_username,
                "connect_mode": "password",
            },
        )

    if request.method != "POST":
        return redirect("profile")

    chess_username = (request.POST.get("chess_username") or "").strip()
    chess_password = request.POST.get("chess_password") or ""
    connect_mode = (request.POST.get("connect_mode") or "password").strip().lower()
    valid_modes = {"password", "interactive"}
    if connect_mode not in valid_modes:
        connect_mode = "password"

    if not chess_username:
        return render(
            request,
            "connect_chess.html",
            {
                "error": "Chess.com username is required.",
                "chess_username": chess_username or default_username,
                "connect_mode": connect_mode,
            },
        )

    try:
        if connect_mode == "interactive":
            integration = collect_chess_credentials_interactive(
                chess_username=chess_username,
            )
        else:
            if not chess_password:
                return render(
                    request,
                    "connect_chess.html",
                    {
                        "error": "Chess.com password is required for password mode.",
                        "chess_username": chess_username,
                        "connect_mode": connect_mode,
                    },
                )

            integration = collect_chess_credentials(
                chess_username=chess_username,
                chess_password=chess_password,
            )
    except ChessIntegrationError as error:
        logger.warning(
            "Chess connect failed: user_id=%s mode=%s chess_username=%s detail=%s",
            request.user.id,
            connect_mode,
            chess_username,
            error,
        )
        user_message = str(error).strip() or (
            "Connection was not completed. Please try again."
            if connect_mode == "password"
            else "Connection was canceled or interrupted. Please try again and keep the browser window open."
        )
        return render(
            request,
            "connect_chess.html",
            {
                "error": user_message,
                "chess_username": chess_username,
                "connect_mode": connect_mode,
            },
        )

    player = _get_or_create_chess_player_for_user(request.user)
    username_owner = (
        ChessPlayer.objects.filter(chess_username=integration.chess_username)
        .exclude(pk=player.pk)
        .first()
    )
    if username_owner:
        return render(
            request,
            "connect_chess.html",
            {
                "error": "This Chess.com username is already connected to another platform user.",
                "chess_username": chess_username,
                "connect_mode": connect_mode,
            },
        )

    player.chess_username = integration.chess_username
    player.chess_profile_url = f"https://www.chess.com/member/{integration.chess_username}"
    player.chess_uuid = integration.chess_uuid
    player.chess_cookie_header = integration.chess_cookie_header
    player.chess_csrf_token = integration.chess_csrf_token
    player.save()
    return redirect(f"{reverse('profile')}?chess_connected=1")


@login_required
def accept_lobby_invite(request, lobby_id: int):
    if request.method != "POST":
        return redirect("lobby")

    lobby_obj = get_object_or_404(GameLobby, pk=lobby_id)
    if lobby_obj.status != GameLobby.Status.INVITED or lobby_obj.guest_id is not None:
        return _render_lobby_page(request, error="This lobby is no longer open.")

    guest = _get_or_create_chess_player_for_user(request.user)
    if lobby_obj.host_id == guest.id:
        return _render_lobby_page(request, error="You cannot accept your own lobby.")

    lobby_obj.guest = guest
    lobby_obj.status = GameLobby.Status.ACTIVE
    if not lobby_obj.started_at:
        lobby_obj.started_at = timezone.now()
    lobby_obj.save()
    return redirect("lobby")


@login_required
def finish_lobby(request, lobby_id: int):
    if request.method != "POST":
        return redirect("lobby")

    lobby_obj = get_object_or_404(GameLobby, pk=lobby_id)
    winner_username = (request.POST.get("winner_username") or "").strip().lower()
    game_url = (request.POST.get("game_url") or "").strip()

    winner = None
    if winner_username:
        winner = get_object_or_404(ChessPlayer, chess_username=winner_username)

    lobby_obj.status = GameLobby.Status.FINISHED
    lobby_obj.winner = winner
    if game_url:
        lobby_obj.chess_game_url = game_url
    lobby_obj.finished_at = timezone.now()
    lobby_obj.save()
    return redirect("lobby")
    
@login_required
def send_chess_invite(request, lobby_id: int):
    if request.method != "POST":
        return redirect("lobby")

    lobby_obj = get_object_or_404(
        GameLobby.objects.select_related("host", "guest"),
        pk=lobby_id,
    )
    current_player = _get_or_create_chess_player_for_user(request.user)

    if lobby_obj.host_id != current_player.id:
        return _render_lobby_page(request, error="Only lobby host can send Chess invite.")
    if lobby_obj.guest is None:
        return _render_lobby_page(request, error="Guest is not assigned yet.")
    return _render_lobby_page(
        request,
        error=(
            "Automatic invite is disabled: Chess.com Public API does not support sending invites. "
            "Open Chess.com Play and send the challenge manually."
        ),
    )

@login_required
def accept_chess_invite(request, lobby_id: int):
    if request.method != "POST":
        return redirect("lobby")

    lobby_obj = get_object_or_404(
        GameLobby.objects.select_related("guest", "host"),
        pk=lobby_id,
    )
    current_player = _get_or_create_chess_player_for_user(request.user)

    if lobby_obj.guest_id != current_player.id:
        return _render_lobby_page(request, error="Only lobby guest can accept Chess invite.")
    return _render_lobby_page(
        request,
        error=(
            "Automatic accept is disabled: Chess.com Public API does not support accepting invites. "
            "Open Chess.com Play and accept the challenge manually."
        ),
    )

