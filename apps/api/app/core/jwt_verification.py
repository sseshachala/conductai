"""Shared JWT signature and registered-claim checks, independent of key transport."""
import jwt


def decode_rs256(token: str, key, issuer: str, audience: str, *, leeway: int = 30) -> dict:
    return jwt.decode(
        token, key=key, algorithms=["RS256"], audience=audience, issuer=issuer,
        leeway=leeway, options={"require": ["exp", "iss", "aud", "sub"]},
    )
