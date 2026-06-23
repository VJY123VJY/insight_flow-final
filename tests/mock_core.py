from jose import jwt
import time
from typing import Dict, Any

# Mock Keys (Development/Demo only)
MOCK_PRIVATE_KEY = {
    "kty": "RSA",
    "d": "...", # Hidden for brevity, I'll use a simpler mock or just RS256 with generated keys
}

# For simplicity in demo, we'll use a fast mock
SECRET = "demo-secret-not-for-prod" # Using HS256 for easy demo if RS256 is too heavy to setup in script

def generate_mock_token(sub: str, aud: str, iss: str, jti: str = None, expired: bool = False):
    now = time.time()
    payload = {
        "sub": sub,
        "aud": aud,
        "iss": iss,
        "iat": now,
        "exp": now - 3600 if expired else now + 3600,
        "jti": jti or str(time.time()),
        "roles": ["demo-user"]
    }
    # In a real demo, this matches CORE_ISSUER
    return jwt.encode(payload, "secret", algorithm="HS256")

# Since SovereignAuth is hardcoded to RS256 for Sovereign Core, I should probably 
# update the security implementation to support HS256 for demo OR generate a real RSA key.
# Let's generate a real RSA key for the demo to be authentic.
