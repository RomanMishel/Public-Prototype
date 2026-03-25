from django.contrib import admin
from django.db.models import Count

from .models import ChessPlayer, GameLobby


@admin.register(ChessPlayer)
class ChessPlayerAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "chess_username",
        "chess_profile_url",
        "hosted_lobbies_count",
        "guest_lobbies_count",
        "won_lobbies_count",
        "created_at",
    )
    search_fields = ("chess_username", "user__username")
    readonly_fields = ("created_at",)
    ordering = ("chess_username",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            hosted_count=Count("hosted_lobbies", distinct=True),
            guest_count=Count("guest_lobbies", distinct=True),
            won_count=Count("won_lobbies", distinct=True),
        )

    @admin.display(ordering="hosted_count", description="Hosted")
    def hosted_lobbies_count(self, obj):
        return obj.hosted_count

    @admin.display(ordering="guest_count", description="Joined")
    def guest_lobbies_count(self, obj):
        return obj.guest_count

    @admin.display(ordering="won_count", description="Won")
    def won_lobbies_count(self, obj):
        return obj.won_count


@admin.register(GameLobby)
class GameLobbyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "short_code",
        "game_type",
        "host",
        "guest_or_open",
        "status",
        "winner",
        "created_at",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "game_type", "created_at", "started_at")
    search_fields = (
        "code",
        "host__chess_username",
        "guest__chess_username",
        "winner__chess_username",
        "chess_game_url",
    )
    list_select_related = ("host", "guest", "winner")
    autocomplete_fields = ("host", "guest", "winner")
    readonly_fields = ("code", "created_at", "updated_at", "started_at", "finished_at")
    ordering = ("-created_at",)
    fieldsets = (
        ("Lobby", {"fields": ("code", "game_type", "status")}),
        ("Players", {"fields": ("host", "guest", "winner")}),
        ("Match", {"fields": ("chess_game_url",)}),
        ("Timeline", {"fields": ("created_at", "updated_at", "started_at", "finished_at")}),
    )

    @admin.display(description="Code")
    def short_code(self, obj):
        return str(obj.code)[:8]

    @admin.display(ordering="guest", description="Guest")
    def guest_or_open(self, obj):
        return obj.guest or "open"
