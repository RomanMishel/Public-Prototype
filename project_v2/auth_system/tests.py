from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import GameLobby


class LobbyFlowTests(TestCase):
    def setUp(self):
        self.platform_user = User.objects.create_user(username="owner", password="pass12345")
        self.client.login(username="owner", password="pass12345")

    # def test_seed_default_players_creates_known_profiles(self):
    #     response = self.client.post(reverse("seed_default_players"))

    #     self.assertEqual(response.status_code, 302)
    #     self.assertTrue(ChessPlayer.objects.filter(chess_username="qd35n1q").exists())
    #     self.assertTrue(ChessPlayer.objects.filter(chess_username="romanatchess").exists())

    def test_create_open_lobby_then_accept(self):
        create_form_response = self.client.get(reverse("create_lobby"))
        self.assertEqual(create_form_response.status_code, 200)

        create_response = self.client.post(
            reverse("create_lobby"),
            data={"game_type": GameLobby.GameType.CHESS},
        )
        self.assertEqual(create_response.status_code, 302)

        lobby = GameLobby.objects.get()
        self.assertEqual(lobby.status, GameLobby.Status.INVITED)
        self.assertEqual(lobby.game_type, GameLobby.GameType.CHESS)
        self.assertEqual(lobby.host.chess_username, "owner")
        self.assertIsNone(lobby.guest)

        challenger = User.objects.create_user(username="challenger", password="pass12345")
        self.client.login(username="challenger", password="pass12345")

        accept_response = self.client.post(reverse("accept_lobby_invite", args=[lobby.id]))
        self.assertEqual(accept_response.status_code, 302)

        lobby.refresh_from_db()
        self.assertEqual(lobby.status, GameLobby.Status.ACTIVE)
        self.assertEqual(lobby.guest.chess_username, challenger.username)
        self.assertIsNotNone(lobby.started_at)

    def test_user_cannot_accept_own_lobby(self):
        self.client.post(
            reverse("create_lobby"),
            data={"game_type": GameLobby.GameType.CHESS},
        )
        lobby = GameLobby.objects.get()

        response = self.client.post(reverse("accept_lobby_invite", args=[lobby.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You cannot accept your own lobby.")

        lobby.refresh_from_db()
        self.assertEqual(lobby.status, GameLobby.Status.INVITED)
        self.assertIsNone(lobby.guest)

    def test_requires_auth_for_lobby_pages(self):
        self.client.logout()
        response = self.client.get(reverse("lobby"))
        self.assertEqual(response.status_code, 302)
        create_response = self.client.get(reverse("create_lobby"))
        self.assertEqual(create_response.status_code, 302)

    def test_second_user_cannot_accept_already_taken_lobby(self):
        self.client.post(
            reverse("create_lobby"),
            data={"game_type": GameLobby.GameType.CHESS},
        )
        lobby = GameLobby.objects.get()

        User.objects.create_user(username="challenger", password="pass12345")
        self.client.login(username="challenger", password="pass12345")
        accept_response = self.client.post(reverse("accept_lobby_invite", args=[lobby.id]))
        self.assertEqual(accept_response.status_code, 302)

        User.objects.create_user(username="third_user", password="pass12345")
        self.client.login(username="third_user", password="pass12345")
        second_accept_response = self.client.post(reverse("accept_lobby_invite", args=[lobby.id]))
        self.assertEqual(second_accept_response.status_code, 200)
        self.assertContains(second_accept_response, "This lobby is no longer open.")

        lobby.refresh_from_db()
        self.assertEqual(lobby.status, GameLobby.Status.ACTIVE)
        self.assertEqual(lobby.guest.chess_username, "challenger")

    def test_players_can_accept_each_others_lobbies(self):
        self.client.post(
            reverse("create_lobby"),
            data={"game_type": GameLobby.GameType.CHESS},
        )
        owner_lobby = GameLobby.objects.get(host__chess_username="owner")

        User.objects.create_user(username="challenger", password="pass12345")
        self.client.login(username="challenger", password="pass12345")
        self.client.post(
            reverse("create_lobby"),
            data={"game_type": GameLobby.GameType.CHESS},
        )
        challenger_lobby = GameLobby.objects.get(host__chess_username="challenger")

        accept_owner_lobby = self.client.post(reverse("accept_lobby_invite", args=[owner_lobby.id]))
        self.assertEqual(accept_owner_lobby.status_code, 302)

        self.client.login(username="owner", password="pass12345")
        accept_challenger_lobby = self.client.post(
            reverse("accept_lobby_invite", args=[challenger_lobby.id])
        )
        self.assertEqual(accept_challenger_lobby.status_code, 302)

        owner_lobby.refresh_from_db()
        challenger_lobby.refresh_from_db()

        self.assertEqual(owner_lobby.status, GameLobby.Status.ACTIVE)
        self.assertEqual(challenger_lobby.status, GameLobby.Status.ACTIVE)
        self.assertEqual(owner_lobby.host.chess_username, "owner")
        self.assertEqual(owner_lobby.guest.chess_username, "challenger")
        self.assertEqual(challenger_lobby.host.chess_username, "challenger")
        self.assertEqual(challenger_lobby.guest.chess_username, "owner")
