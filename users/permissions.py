from rest_framework.permissions import BasePermission, SAFE_METHODS


def is_super_admin(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.role == "super_admin"
        )
    )


def has_agency(user):
    return bool(
        user
        and user.is_authenticated
        and user.agency_id is not None
    )


def is_agency_owner(user):
    return bool(
        has_agency(user)
        and user.role == "agency_owner"
    )


def is_agency_manager(user):
    return bool(
        has_agency(user)
        and user.role == "agency_manager"
    )


def is_agency_owner_or_manager(user):
    return bool(
        has_agency(user)
        and user.role in [
            "agency_owner",
            "agency_manager",
        ]
    )


def is_agent(user):
    return bool(
        has_agency(user)
        and user.role == "agent"
    )


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_super_admin(request.user)


class IsAgencyOwner(BasePermission):
    def has_permission(self, request, view):
        return is_agency_owner(request.user)


class IsAgencyOwnerOrManager(BasePermission):
    def has_permission(self, request, view):
        return is_agency_owner_or_manager(request.user)


class IsAgencyOwnerOrManagerOrReadOnly(BasePermission):
    """Allow agency users to read shared configuration, but restrict mutations."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return has_agency(request.user) or is_super_admin(request.user)

        return is_agency_owner_or_manager(request.user) or is_super_admin(request.user)


class IsAgent(BasePermission):
    def has_permission(self, request, view):
        return is_agent(request.user)
