from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class AgencyJWTAuthentication(JWTAuthentication):
    """Reject valid tokens when the user or agency can no longer access the product."""

    def authenticate(self, request):
        authenticated = super().authenticate(request)
        if authenticated is None:
            return None

        user, token = authenticated
        if user.is_superuser or user.role == user.ROLE_SUPER_ADMIN:
            return user, token

        if not user.agency_id:
            raise AuthenticationFailed("This user is not linked to an agency.")

        if not user.agency.has_active_subscription:
            raise AuthenticationFailed("Agency subscription is inactive or expired.")

        return user, token
