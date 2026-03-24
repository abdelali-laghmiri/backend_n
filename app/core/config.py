from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.shared.enums import EnvironmentEnum


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    project_name: str = Field(
        default="HR Management Backend",
        validation_alias=AliasChoices("PROJECT_NAME", "APP_NAME"),
    )
    project_version: str = Field(
        default="0.1.0",
        validation_alias=AliasChoices("PROJECT_VERSION", "APP_VERSION"),
    )
    project_description: str = Field(
        default="Modular FastAPI backend skeleton for an HR management system.",
        validation_alias=AliasChoices("PROJECT_DESCRIPTION", "APP_DESCRIPTION"),
    )
    app_env: EnvironmentEnum = Field(
        default=EnvironmentEnum.DEVELOPMENT,
        validation_alias=AliasChoices("APP_ENV", "APP_ENVIRONMENT"),
    )
    debug: bool = Field(
        default=True,
        validation_alias=AliasChoices("DEBUG", "APP_DEBUG"),
    )
    secret_key: SecretStr = Field(
        default=SecretStr("change-this-secret-in-production"),
        validation_alias="SECRET_KEY",
    )
    api_v1_prefix: str = Field(
        default="/api/v1",
        validation_alias=AliasChoices("API_V1_PREFIX", "APP_API_V1_PREFIX"),
    )
    app_host: str = Field(default="0.0.0.0", validation_alias="APP_HOST")
    app_port: int = Field(default=8000, validation_alias="APP_PORT")
    forwarded_allow_ips: str = Field(
        default="127.0.0.1",
        validation_alias="FORWARDED_ALLOW_IPS",
    )
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
        gt=0,
    )
    db_echo: bool = Field(
        default=False,
        validation_alias=AliasChoices("DB_ECHO", "APP_DB_ECHO"),
    )

    database_url: str | None = Field(
        default="sqlite:///./hr_management.db",
        validation_alias="DATABASE_URL",
    )
    postgres_host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("POSTGRES_HOST", "POSTGRES_SERVER"),
    )
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    postgres_db: str = Field(default="hr_management", validation_alias="POSTGRES_DB")
    postgres_user: str = Field(default="postgres", validation_alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(
        default=SecretStr("postgres"),
        validation_alias="POSTGRES_PASSWORD",
    )
    superadmin_matricule: str | None = Field(
        default=None,
        validation_alias="SUPERADMIN_MATRICULE",
    )
    superadmin_password: SecretStr | None = Field(
        default=None,
        validation_alias="SUPERADMIN_PASSWORD",
    )
    superadmin_first_name: str | None = Field(
        default=None,
        validation_alias="SUPERADMIN_FIRST_NAME",
    )
    superadmin_last_name: str | None = Field(
        default=None,
        validation_alias="SUPERADMIN_LAST_NAME",
    )
    superadmin_email: str | None = Field(
        default=None,
        validation_alias="SUPERADMIN_EMAIL",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> str | None:
        """Normalize blank database URLs to None."""

        if value is None:
            return None

        if isinstance(value, str):
            stripped_value = value.strip()
            return stripped_value or None

        return str(value)

    @field_validator("debug", "db_echo", mode="before")
    @classmethod
    def parse_boolean_values(cls, value: object) -> bool:
        """Accept a practical range of boolean environment values."""

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return bool(value)

        if isinstance(value, str):
            normalized = value.strip().lower()
            truthy_values = {"1", "true", "t", "yes", "y", "on"}
            falsy_values = {"0", "false", "f", "no", "n", "off", "", "release"}

            if normalized in truthy_values:
                return True

            if normalized in falsy_values:
                return False

        raise ValueError("Expected a boolean-compatible value.")

    @field_validator("database_url")
    @classmethod
    def normalize_postgres_driver(cls, value: str | None) -> str | None:
        """Force PostgreSQL URLs to use the psycopg driver shipped with the project."""

        if value is None:
            return None

        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)

        if value.startswith("postgresql://") and "+psycopg" not in value:
            return value.replace("postgresql://", "postgresql+psycopg://", 1)

        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        """Limit JWT signing to the supported algorithm."""

        normalized_value = value.strip().upper()
        if normalized_value != "HS256":
            raise ValueError("Only HS256 is supported for JWT tokens.")

        return normalized_value

    def get_database_url(self) -> str:
        """Return the configured database URL."""

        if self.database_url:
            return self.database_url

        username = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password.get_secret_value())
        return (
            f"postgresql+psycopg://{username}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def get_super_admin_bootstrap(self) -> dict[str, str]:
        """Return validated bootstrap values for the first super admin."""

        raw_password = (
            self.superadmin_password.get_secret_value()
            if self.superadmin_password is not None
            else ""
        )
        raw_values = {
            "SUPERADMIN_MATRICULE": self.superadmin_matricule or "",
            "SUPERADMIN_PASSWORD": raw_password,
            "SUPERADMIN_FIRST_NAME": self.superadmin_first_name or "",
            "SUPERADMIN_LAST_NAME": self.superadmin_last_name or "",
            "SUPERADMIN_EMAIL": self.superadmin_email or "",
        }
        missing_variables = [
            variable_name
            for variable_name, raw_value in raw_values.items()
            if not raw_value.strip()
        ]
        if missing_variables:
            missing_list = ", ".join(missing_variables)
            raise ValueError(
                f"Missing required bootstrap environment variables: {missing_list}."
            )

        return {
            "matricule": raw_values["SUPERADMIN_MATRICULE"].strip(),
            "password": raw_password,
            "first_name": raw_values["SUPERADMIN_FIRST_NAME"].strip(),
            "last_name": raw_values["SUPERADMIN_LAST_NAME"].strip(),
            "email": raw_values["SUPERADMIN_EMAIL"].strip().lower(),
        }

    @property
    def is_sqlite(self) -> bool:
        """Check whether the active database backend is SQLite."""

        return self.get_database_url().startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
