"""LLM gateway: every model call goes through here so usage and cost are recorded in one place."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import anthropic
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .llm_profiles import ModelProfile, load_profiles
from .models import UsageRecord

MAX_TOKENS = 16000
CACHE_READ_RATE = 0.1
CACHE_WRITE_RATE = 1.25


class LLMError(Exception):
    """A model call that cannot be made or failed for good; the message is shown to the office head."""


@dataclass
class Model:
    profile: ModelProfile
    client: anthropic.Anthropic

    def create(self, **kwargs: Any):
        try:
            return self.client.messages.create(model=self.profile.model, max_tokens=MAX_TOKENS, **kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMError("APIキーが正しくありません（.env を確認してください）") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("このモデルを使う権限がありません") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"モデル「{self.profile.model}」が見つかりません（config/models.yaml を確認してください）") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"リクエストが受け付けられませんでした: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("利用上限に達しました。しばらく待ってから再実行してください") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"LLMサービスのエラー（{exc.status_code}）。時間をおいて再実行してください") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("LLMサービスに接続できませんでした") from exc


def open_model(profile_name: str) -> Model:
    settings = get_settings()
    profile = next((p for p in load_profiles(settings) if p.name == profile_name), None)
    if profile is None:
        raise LLMError(f"モデルプロファイル「{profile_name}」がありません")
    if not profile.available:
        raise LLMError(f"モデル「{profile.label}」は使えません: {profile.reason}")
    if profile.provider == "anthropic":
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3, timeout=300)
    elif profile.provider == "bedrock":
        client = anthropic.AnthropicBedrockMantle(aws_region=settings.aws_region, max_retries=3, timeout=300)
    else:
        raise LLMError(f"{profile.provider} の呼び出しはまだ実装されていません")
    return Model(profile=profile, client=client)


def record_usage(session: Session, model: Model, response, *, agent_id: int | None, project_id: int | None,
                 task_id: int | None, run_id: int | None) -> Decimal:
    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    price_in = model.profile.price_input or 0.0
    price_out = model.profile.price_output or 0.0
    server = getattr(usage, "server_tool_use", None)
    searches = (getattr(server, "web_search_requests", 0) or 0) if server else 0
    cost = Decimal(str(
        (usage.input_tokens * price_in + usage.output_tokens * price_out
         + cache_read * price_in * CACHE_READ_RATE + cache_write * price_in * CACHE_WRITE_RATE) / 1_000_000
        + searches * get_settings().web_search_price_usd
    )).quantize(Decimal("0.000001"))
    session.add(UsageRecord(
        agent_id=agent_id, project_id=project_id, task_id=task_id, run_id=run_id,
        model_profile=model.profile.name, model=model.profile.model,
        input_tokens=usage.input_tokens + cache_read + cache_write, output_tokens=usage.output_tokens,
        cache_read_tokens=cache_read, cache_write_tokens=cache_write, cost_usd=cost,
    ))
    return cost


def month_spend(session: Session) -> Decimal:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return session.scalar(select(func.coalesce(func.sum(UsageRecord.cost_usd), 0)).where(
        UsageRecord.created_at >= start)) or Decimal(0)


def check_budget(session: Session) -> None:
    budget = get_settings().monthly_budget_usd
    if budget > 0 and month_spend(session) >= Decimal(str(budget)):
        raise LLMError(f"今月の予算（${budget:.2f}）に達したため、新しい処理を止めました。.env の MONTHLY_BUDGET_USD で変更できます")
