from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field


class DhanConfig(BaseModel):
    client_id: str = Field(default="")
    pin: str = Field(default="")
    totp_secret: str = Field(default="")
    api_url: str = Field(default="https://api.dhan.co")
    auth_url: str = Field(default="https://auth.dhan.co")
    instruments_compact_url: str = Field(
        default="https://images.dhan.co/api-data/api-scrip-master.csv"
    )


class UpstoxConfig(BaseModel):
    client_id: str = Field(default="")
    client_secret: str = Field(default="")
    redirect_uri: str = Field(default="")
    mobile: str = Field(default="")
    pin: str = Field(default="")
    totp_secret: str = Field(default="")


class AppConfig(BaseSettings):
    environment: str = Field(default="production")
    log_level: str = Field(default="INFO")

    dhan: DhanConfig = Field(default_factory=DhanConfig)
    upstox: UpstoxConfig = Field(default_factory=UpstoxConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


# Global singleton for settings
settings = AppConfig()
