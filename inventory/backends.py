from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username:
            return None
        login_input = username.strip()

        try:
            user = User.objects.get(email=login_input.lower())
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            pass
        except User.MultipleObjectsReturned:
            user = User.objects.filter(email=login_input.lower()).order_by('id').first()
            if user and user.check_password(password):
                return user

        from .models import Profile
        cashier_profiles = Profile.objects.filter(
            role=Profile.ROLE_CASHIER, nickname=login_input
        ).select_related('user')
        for profile in cashier_profiles:
            if profile.user.check_password(password):
                return profile.user

        return None
