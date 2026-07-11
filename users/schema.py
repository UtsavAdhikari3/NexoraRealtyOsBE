from drf_spectacular.extensions import OpenApiAuthenticationExtension


class AgencyJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "users.authentication.AgencyJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
