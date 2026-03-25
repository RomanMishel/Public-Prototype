import uuid

from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ChessPlayer(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="chess_player",
        null=True,
        blank=True,
        unique=True,
    )
    chess_username = models.CharField(max_length=64, unique=True)
    chess_profile_url = models.URLField(unique=True)
    chess_uuid = models.CharField(max_length=64, blank=True, db_index=True)
    chess_cookie_header = models.TextField(blank=True)   # MVP: Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ðµ cookie ÐºÐ°Ðº ÑÑ‚Ñ€Ð¾ÐºÐ°
    chess_csrf_token = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("chess_username",)

    def save(self, *args, **kwargs):
        username = (self.chess_username or "").strip().lower()
        if not username:
            raise ValidationError("chess_username is required.")
        self.chess_username = username
        if not self.chess_profile_url:
            self.chess_profile_url = f"https://www.chess.com/member/{username}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.chess_username


class GameLobby(models.Model):
    class Status(models.TextChoices):
        INVITED = "invited", "Invited"
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"
        CANCELLED = "cancelled", "Cancelled"

    class GameType(models.TextChoices):
        CHESS = "chess", "Chess"

    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    game_type = models.CharField(max_length=16, choices=GameType.choices, default=GameType.CHESS)
    stake_amount = models.PositiveIntegerField(default=1)
    host = models.ForeignKey(
        ChessPlayer,
        on_delete=models.CASCADE,
        related_name="hosted_lobbies",
    )
    guest = models.ForeignKey(
        ChessPlayer,
        on_delete=models.CASCADE,
        related_name="guest_lobbies",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INVITED)
    chess_game_url = models.URLField(blank=True)
    chess_challenge_id = models.CharField(max_length=64, blank=True, db_index=True)
    chess_game_id = models.CharField(max_length=64, blank=True, db_index=True)
    chess_game_legacy_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    chess_state = models.CharField(max_length=32, blank=True)
    winner = models.ForeignKey(
        ChessPlayer,
        on_delete=models.SET_NULL,
        related_name="won_lobbies",
        null=True,
        blank=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        if self.host_id and self.guest_id and self.host_id == self.guest_id:
            raise ValidationError("Host and guest must be different players.")
        if self.winner_id and self.winner_id not in {self.host_id, self.guest_id}:
            raise ValidationError("Winner must be one of lobby players.")
        if self.stake_amount < 1:
            raise ValidationError("Stake must be at least 1.")
        if self.status == self.Status.FINISHED and not self.finished_at:
            self.finished_at = timezone.now()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        guest = self.guest or "open"
        return f"{self.get_game_type_display()}: {self.host} vs {guest} [{self.status}]"

