"""Synthetic custom auth for the real LiteLLM harness; not a customer auth recipe."""
import json
import os

import jwt
from fastapi import HTTPException
from litellm.proxy._types import UserAPIKeyAuth
from conduct_litellm_guard.auth import with_subject_token
from conduct_litellm_guard import ConductGuard


async def authenticate(request, api_key):
    try:
        key = jwt.algorithms.RSAAlgorithm.from_jwk(os.environ["FIXTURE_JWK"])
        claims = jwt.decode(api_key, key, algorithms=["RS256"],
                            issuer=os.environ["FIXTURE_ISSUER"], audience=os.environ["FIXTURE_AUDIENCE"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Fixture authentication denied") from None
    return with_subject_token(UserAPIKeyAuth(user_id=claims["sub"]), api_key)


PilotGuard = ConductGuard
