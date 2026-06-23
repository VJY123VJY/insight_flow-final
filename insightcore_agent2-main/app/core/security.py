import httpx
from jose import jwt, JWTError
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings
import logging
import time

logger = logging.getLogger(__name__)

security = HTTPBearer()

class SovereignAuth:
    _jwks_cache = None
    _last_fetch = 0
    CACHE_TTL = 3600  # 1 hour

    @classmethod
    async def get_jwks(cls):
        if cls._jwks_cache and (time.time() - cls._last_fetch < cls.CACHE_TTL):
            return cls._jwks_cache
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(settings.CORE_JWKS_URL)
                if response.status_code == 200:
                    cls._jwks_cache = response.json()
                    cls._last_fetch = time.time()
                    return cls._jwks_cache
                else:
                    logger.error(f"Failed to fetch JWKS from Core: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error connecting to Sovereign Core: {e}")
            return None

    @classmethod
    async def verify_token(cls, credentials: HTTPAuthorizationCredentials = Security(security)):
        token = credentials.credentials

        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")

            # Local demo token fallback: /login creates HS256 tokens.
            if alg == "HS256":
                from app.auth import verify_access_token

                payload = verify_access_token(token)
                if not payload:
                    raise JWTError("Invalid or expired local token")
                return payload

            jwks = await cls.get_jwks()
            
            # FAIL-CLOSED: If JWKS is unavailable, we cannot verify tokens safely
            if not jwks:
                logger.critical("Sovereign Core unavailable. Denying access (Fail-Closed).")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication Authority Unavailable"
                )

            # Jose library handles header and signature verification
            kid = header.get("kid")
            
            # Find the correct key in JWKS
            key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
            if not key:
                raise JWTError("Public key not found in JWKS")

            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=settings.CORE_AUDIENCE,
                issuer=settings.CORE_ISSUER
            )
            return payload
        except JWTError as e:
            logger.warning(f"JWT Validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired security token"
            )
        except Exception as e:
            logger.error(f"Unexpected error during token verification: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security validation error"
            )
