from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


class PasswordManager:
    """Reusable password hashing utility based on scrypt."""

    algorithm = "scrypt"
    salt_size = 16
    n = 2**14
    r = 8
    p = 1
    dklen = 64

    @classmethod
    def hash_password(cls, password: str) -> str:
        """Hash a plaintext password with a random salt."""

        normalized_password = cls._validate_password(password)
        salt = secrets.token_bytes(cls.salt_size)
        derived_key = hashlib.scrypt(
            normalized_password.encode("utf-8"),
            salt=salt,
            n=cls.n,
            r=cls.r,
            p=cls.p,
            dklen=cls.dklen,
        )
        return (
            f"{cls.algorithm}${cls.n}${cls.r}${cls.p}${cls.dklen}$"
            f"{base64.b64encode(salt).decode('ascii')}$"
            f"{base64.b64encode(derived_key).decode('ascii')}"
        )

    @classmethod
    def verify_password(cls, plain_password: str, password_hash: str) -> bool:
        """Verify a plaintext password against a stored password hash."""

        try:
            normalized_password = cls._validate_password(plain_password)
        except (TypeError, ValueError):
            return False

        try:
            algorithm, n_value, r_value, p_value, dklen_value, salt_b64, hash_b64 = (
                password_hash.split("$", 6)
            )
            if algorithm != cls.algorithm:
                return False

            salt = base64.b64decode(salt_b64.encode("ascii"), validate=True)
            expected_hash = base64.b64decode(hash_b64.encode("ascii"), validate=True)
            derived_key = hashlib.scrypt(
                normalized_password.encode("utf-8"),
                salt=salt,
                n=int(n_value),
                r=int(r_value),
                p=int(p_value),
                dklen=int(dklen_value),
            )
        except (TypeError, ValueError):
            return False

        return hmac.compare_digest(derived_key, expected_hash)

    @staticmethod
    def _validate_password(password: str) -> str:
        """Validate password input before hashing or verification."""

        if not isinstance(password, str):
            raise TypeError("Password value must be a string.")

        if password == "":
            raise ValueError("Password value cannot be empty.")

        return password


class TokenValidationError(RuntimeError):
    """Raised when a JWT cannot be parsed or trusted."""


class JWTManager:
    """Reusable JWT utilities for access token handling."""

    token_type = "access"

    @classmethod
    def create_access_token(
        cls,
        *,
        subject: str,
        secret_key: str,
        expires_delta: timedelta,
        algorithm: str,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create a signed JWT access token."""

        if not subject:
            raise ValueError("JWT subject cannot be empty.")

        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": subject,
            "type": cls.token_type,
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
        }
        if extra_claims:
            payload.update(extra_claims)

        header = {"alg": algorithm, "typ": "JWT"}
        signing_input = ".".join(
            [
                cls._encode_segment(header),
                cls._encode_segment(payload),
            ]
        )
        signature = cls._sign(
            signing_input=signing_input,
            secret_key=secret_key,
            algorithm=algorithm,
        )
        return f"{signing_input}.{signature}"

    @classmethod
    def decode_token(
        cls,
        *,
        token: str,
        secret_key: str,
        algorithm: str,
    ) -> dict[str, Any]:
        """Validate and decode a signed JWT access token."""

        try:
            header_segment, payload_segment, signature_segment = token.split(".")
        except ValueError as exc:
            raise TokenValidationError("Token structure is invalid.") from exc

        header = cls._decode_segment(header_segment)
        payload = cls._decode_segment(payload_segment)

        if header.get("alg") != algorithm:
            raise TokenValidationError("Token algorithm is invalid.")

        expected_signature = cls._sign(
            signing_input=f"{header_segment}.{payload_segment}",
            secret_key=secret_key,
            algorithm=algorithm,
        )
        if not hmac.compare_digest(expected_signature, signature_segment):
            raise TokenValidationError("Token signature is invalid.")

        token_type = payload.get("type")
        if token_type != cls.token_type:
            raise TokenValidationError("Token type is invalid.")

        expiration_timestamp = payload.get("exp")
        if not isinstance(expiration_timestamp, int):
            raise TokenValidationError("Token expiration is invalid.")

        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        if expiration_timestamp <= current_timestamp:
            raise TokenValidationError("Token has expired.")

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise TokenValidationError("Token subject is invalid.")

        return payload

    @staticmethod
    def _sign(*, signing_input: str, secret_key: str, algorithm: str) -> str:
        """Sign JWT content with the configured symmetric algorithm."""

        if algorithm != "HS256":
            raise ValueError("Only HS256 is supported for JWT tokens.")

        digest = hmac.new(
            secret_key.encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return JWTManager._base64url_encode(digest)

    @staticmethod
    def _encode_segment(value: dict[str, Any]) -> str:
        """Encode a JWT header or payload segment."""

        raw_bytes = json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return JWTManager._base64url_encode(raw_bytes)

    @staticmethod
    def _decode_segment(value: str) -> dict[str, Any]:
        """Decode a JWT header or payload segment."""

        try:
            raw_bytes = JWTManager._base64url_decode(value)
            decoded_value = json.loads(raw_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TokenValidationError("Token payload is invalid.") from exc

        if not isinstance(decoded_value, dict):
            raise TokenValidationError("Token payload is invalid.")

        return decoded_value

    @staticmethod
    def _base64url_encode(value: bytes) -> str:
        """Encode bytes with URL-safe base64 without padding."""

        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _base64url_decode(value: str) -> bytes:
        """Decode URL-safe base64 with optional missing padding."""

        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}")


def generate_temporary_password(length: int = 12) -> str:
    """Generate a temporary password suitable for first-login onboarding."""

    if length < 8:
        raise ValueError("Temporary password length must be at least 8 characters.")

    alphabet = string.ascii_letters + string.digits + "!@#$%*?"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    """Extract a bearer token without enforcing authentication logic."""

    if credentials is None:
        return None

    return credentials.credentials
