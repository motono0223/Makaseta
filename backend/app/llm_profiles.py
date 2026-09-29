"""Model profiles from config/models.yaml, with whether each one can be used.

Secrets never leave this module: the API only reports whether a credential is present.
"""

from pydantic import BaseModel
import yaml

from .config import Settings

PLACEHOLDER_PREFIX = "REPLACE_WITH_"


class ModelProfile(BaseModel):
    name: str
    label: str
    provider: str
    model: str
    kind: str = "chat"
    supports_tools: bool = False
    available: bool
    reason: str = ""
    is_default: bool = False


def _credential_status(provider: str, settings: Settings) -> tuple[bool, str]:
    if provider == "bedrock":
        has_files = (settings.aws_dir / "credentials").exists() or (settings.aws_dir / "config").exists()
        if has_files or settings.aws_access_key_id:
            return True, ""
        return False, "AWSの認証情報が見つかりません（ホストで aws configure を実行してください）"
    keys = {
        "openai": ("OPENAI_API_KEY", settings.openai_api_key),
        "gemini": ("GEMINI_API_KEY", settings.gemini_api_key),
        "deepseek": ("DEEPSEEK_API_KEY", settings.deepseek_api_key),
    }
    if provider not in keys:
        return False, f"未対応のプロバイダです: {provider}"
    env_name, value = keys[provider]
    if value:
        return True, ""
    return False, f".env に {env_name} が設定されていません"


def load_profiles(settings: Settings) -> list[ModelProfile]:
    path = settings.models_config
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = {settings.default_model_profile, settings.embedding_model_profile}

    profiles = []
    for name, spec in (raw.get("profiles") or {}).items():
        provider = str(spec.get("provider", ""))
        model = str(spec.get("model", ""))
        available, reason = _credential_status(provider, settings)
        if available and (not model or model.startswith(PLACEHOLDER_PREFIX)):
            available, reason = False, "config/models.yaml の model が未記入です"
        profiles.append(
            ModelProfile(
                name=name,
                label=str(spec.get("label", name)),
                provider=provider,
                model=model,
                kind=str(spec.get("kind", "chat")),
                supports_tools=bool(spec.get("supports_tools", False)),
                available=available,
                reason=reason,
                is_default=name in defaults,
            )
        )
    return profiles
