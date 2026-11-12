"""Config loading: accounts.yaml (structure) + environment variables (secrets)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ConfigError(Exception):
    pass


def env(name: str | None, required: bool = True) -> str:
    """Resolve a secret from the environment by variable *name*."""
    val = os.environ.get(name or "", "")
    if required and not val:
        raise ConfigError(f"Environment variable {name!r} is not set")
    return val


class Settings(BaseModel):
    lookback_hours: int = 24
    triage_model: str = "claude-haiku-5-5"
    synthesis_model: str = "claude-sonnet-5-5"
    llm_backend: Literal["sdk", "cli"] = "sdk"
    max_emails_per_run: int = 100
    max_daily_budget_usd: float = 0.15
    vip_domains: list[str] = Field(default_factory=list)
    ignore_senders: list[str] = Field(default_factory=list)
    # Optional override: {"model-id": [input_usd_per_mtok, output_usd_per_mtok]}
    pricing_per_mtok: dict[str, tuple[float, float]] = Field(default_factory=dict)


class Delivery(BaseModel):
    enabled: bool = True
    method: Literal["smtp", "gmail", "graph"] = "smtp"
    recipient_env: str = "REPORT_RECIPIENT_EMAIL"
    sender_env: str = "REPORT_SENDER_EMAIL"
    # smtp
    smtp_host: str = "smtp.mail.yahoo.com"
    smtp_port: int = 465
    smtp_user_env: str | None = None  # defaults to the sender address
    smtp_password_env: str = "YAHOO_APP_PASSWORD"
    # gmail / graph (token needs gmail.send / Mail.Send scope)
    oauth_client_id_env: str | None = None
    oauth_client_secret_env: str | None = None
    oauth_refresh_token_env: str | None = None
    oauth_tenant: str = "common"


class Account(BaseModel):
    id: str
    provider: Literal["gmail", "outlook", "yahoo"]
    enabled: bool = True
    client_id_env: str | None = None
    client_secret_env: str | None = None
    refresh_token_env: str | None = None
    tenant: str = "common"  # outlook only
    username_env: str | None = None  # yahoo
    password_env: str | None = None  # yahoo app password

    @model_validator(mode="after")
    def _needs(self):
        need = {
            "gmail": ["client_id_env", "client_secret_env", "refresh_token_env"],
            "outlook": ["client_id_env", "refresh_token_env"],
            "yahoo": ["username_env", "password_env"],
        }[self.provider]
        missing = [f for f in need if not getattr(self, f)]
        if missing:
            raise ValueError(f"account {self.id!r} ({self.provider}) missing: {', '.join(missing)}")
        return self


class Config(BaseModel):
    settings: Settings = Field(default_factory=Settings)
    delivery: Delivery = Field(default_factory=Delivery)
    accounts: list[Account] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [a.id for a in self.accounts]
        if len(ids) != len(set(ids)):
            raise ValueError("account ids must be unique")
        return self


def load_config(path: str | Path) -> Config:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"{p} not found - copy config/accounts.example.yaml to config/accounts.yaml")
    return Config.model_validate(yaml.safe_load(p.read_text()) or {})
