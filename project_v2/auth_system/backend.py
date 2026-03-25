from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        login = username or kwargs.get(UserModel.USERNAME_FIELD) or kwargs.get("email")
        if not login or not password:
            return None

        try:
            user = UserModel.objects.get(Q(username__iexact=login) | Q(email__iexact=login))
        except (UserModel.DoesNotExist, UserModel.MultipleObjectsReturned):
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
