"""Server-side LiteLLM custom-auth handoff; never populate from request metadata.

Call after the host application's authentication succeeds. Conduct independently
verifies this access JWT and its audience, subject and delegation on every call.
Private attributes keep evidence out of LiteLLM's serialized auth metadata.
"""
from litellm.proxy._types import UserAPIKeyAuth
from pydantic import PrivateAttr, SecretStr


class FederatedAuth(UserAPIKeyAuth):
    _conduct_subject: SecretStr | None = PrivateAttr(default=None)


def with_subject_token(auth: UserAPIKeyAuth, access_token: str) -> FederatedAuth:
    if not isinstance(auth, UserAPIKeyAuth) or not isinstance(access_token, str):
        raise ValueError("Authenticated LiteLLM context and access token required")
    if not access_token or len(access_token) > 32768:
        raise ValueError("Invalid subject evidence")
    result = FederatedAuth.model_validate(auth.model_dump())
    result._conduct_subject = SecretStr(access_token)
    return result


def subject_token(auth) -> str | None:
    if isinstance(auth, FederatedAuth) and auth._conduct_subject is not None:
        return auth._conduct_subject.get_secret_value()
    return None
