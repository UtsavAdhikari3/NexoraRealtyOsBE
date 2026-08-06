class AuditMiddleware:
    """Record successful mutations in established modules outside operations."""

    MODULES = {
        "properties": "property",
        "leads": "lead",
        "agents": "agent",
        "site-visits": "site_visit",
        "agencies": "agency",
        "social-posts": "social_post",
        "inbox": "inbox",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"} or not 200 <= response.status_code < 400:
            return response
        user = getattr(request, "user", None)
        agency = getattr(user, "agency", None)
        if not getattr(user, "is_authenticated", False) or not agency or request.path.startswith("/api/operations/"):
            return response
        parts = [part for part in request.path.split("/") if part]
        module = parts[1] if len(parts) > 1 and parts[0] == "api" else ""
        entity_type = self.MODULES.get(module)
        if not entity_type:
            return response
        from .models import AuditLog
        entity_id = next((part for part in reversed(parts) if part.isdigit()), "")
        actions = {"POST": "created", "PUT": "updated", "PATCH": "updated", "DELETE": "deleted"}
        AuditLog.objects.create(
            agency=agency,
            actor=user,
            action=actions[request.method],
            entity_type=entity_type,
            entity_id=entity_id,
            summary=f"{actions[request.method].title()} {entity_type.replace('_', ' ')} via {request.path}",
            ip_address=(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")),
        )
        return response
