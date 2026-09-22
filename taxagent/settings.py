from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_OFF = {"0", "false", "no", "off"}


def _flag(v: object) -> object:
    if isinstance(v, str):
        return v.strip().lower() not in _OFF
    return v


def _secret(v: SecretStr | None) -> str | None:
    return (v.get_secret_value() or None) if v is not None else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True, populate_by_name=True)

    tax: str = Field("pph21", validation_alias="TAXAGENT_TAX")
    data_root: Path = Field(Path("data"), validation_alias="PPH21_DATA")
    log_level: str = Field("WARNING", validation_alias="TAXAGENT_LOG_LEVEL")

    graph_tools: bool = Field(True, validation_alias="PPH21_TOOL_GRAF")
    graph_ablation: bool = Field(False, validation_alias="PPH21_GRAF_ABLASI")
    g5_mode: str = Field("", validation_alias="TAXAGENT_G5_MODE")
    stale_reports_file: Path = Field(Path("monitor_state/permintaan_agent.jsonl"),
                                     validation_alias="PPH21_PERMINTAAN_AGENT")

    monitor_contact: str = Field("", validation_alias="PPH21_PANTAU_KONTAK")
    ocr_cmd: str | None = Field(None, validation_alias="PPH21_OCR_CMD")
    ocr_box_cmd: str | None = Field(None, validation_alias="PPH21_OCR_KOTAK_CMD")
    gemini_embed_dim: int = Field(768, validation_alias="PPH21_GEMINI_DIM")

    llm_provider: str | None = Field(None, validation_alias="LLM_PROVIDER")
    llm_force_no_temperature: str = Field("", validation_alias="LLM_TANPA_TEMPERATURE")
    llm_reasoning_effort: str = Field("none", validation_alias="LLM_REASONING_EFFORT")
    openai_model: str = Field("gpt-4o", validation_alias="OPENAI_MODEL")
    azure_deployment: str | None = Field(None, validation_alias="AZURE_OPENAI_DEPLOYMENT")
    azure_endpoint: str | None = Field(None, validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_api_version: str = Field("2024-10-21", validation_alias="AZURE_OPENAI_API_VERSION")
    azure_api_key_: SecretStr | None = Field(None, validation_alias="AZURE_OPENAI_API_KEY")
    openai_api_key_: SecretStr | None = Field(None, validation_alias="OPENAI_API_KEY")
    google_api_key_: SecretStr | None = Field(None, validation_alias="GOOGLE_API_KEY")

    neo4j_uri: str | None = Field(None, validation_alias="NEO4J_URI")
    neo4j_user: str = Field("neo4j", validation_alias="NEO4J_USER")
    neo4j_password_: SecretStr | None = Field(None, validation_alias="NEO4J_PASSWORD")
    neo4j_database: str = Field("neo4j", validation_alias="NEO4J_DATABASE")
    neo4j_v2_uri: str | None = Field(None, validation_alias="NEO4J_V2_URI")
    neo4j_v2_user: str = Field("neo4j", validation_alias="NEO4J_V2_USER")
    neo4j_v2_password_: SecretStr | None = Field(None, validation_alias="NEO4J_V2_PASSWORD")

    @field_validator("graph_tools", mode="before")
    @classmethod
    def _flags(cls, v: object) -> object:
        return _flag(v)

    @field_validator("log_level", mode="before")
    @classmethod
    def _level(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("monitor_contact", "llm_force_no_temperature", "llm_reasoning_effort", "g5_mode", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @property
    def azure_api_key(self) -> str | None:
        return _secret(self.azure_api_key_)

    @property
    def openai_api_key(self) -> str | None:
        return _secret(self.openai_api_key_)

    @property
    def google_api_key(self) -> str | None:
        return _secret(self.google_api_key_)

    @property
    def neo4j_password(self) -> str | None:
        return _secret(self.neo4j_password_)

    @property
    def neo4j_v2_password(self) -> str | None:
        return _secret(self.neo4j_v2_password_)

    def model_name(self, provider: str) -> str | None:
        return {"azure": self.azure_deployment, "openai": self.openai_model}.get(provider)


def get_settings() -> Settings:
    return Settings()
