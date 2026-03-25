from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('profile/', views.profile, name='profile'),
    path('profile/connect-chess/', views.connect_chess_account, name='connect_chess_account'),
    path("logout/", views.logout, name="logout"),
    path("lobby/", views.lobby, name="lobby"),
    # path("lobby/seed-default-players/", views.seed_default_players, name="seed_default_players"),
    path("lobby/create/", views.create_lobby, name="create_lobby"),
    path("lobby/<int:lobby_id>/accept/", views.accept_lobby_invite, name="accept_lobby_invite"),
    path("lobby/<int:lobby_id>/finish/", views.finish_lobby, name="finish_lobby"),
    path("lobby/<int:lobby_id>/send-chess-invite/", views.send_chess_invite, name="send_chess_invite"),
    path("lobby/<int:lobby_id>/accept-chess-invite/", views.accept_chess_invite, name="accept_chess_invite"),
]
