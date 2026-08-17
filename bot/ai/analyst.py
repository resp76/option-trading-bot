"""Optional LLM analyst: reviews a proposed trade and may veto it.

Works with any OpenAI-compatible endpoint via litellm. Disabled by default.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def ai_review(strategy, signal: dict, cfg: dict) -> tuple[bool, str]:
    """Return (approved, reasoning). On any error, fail OPEN (approve) but log it."""
    ai_cfg = cfg.get("ai_review", {}) or {}
    if not ai_cfg.get("enabled", False):
        return True, "ai_review disabled"

    try:
        import litellm
        from dotenv import load_dotenv
        load_dotenv()

        base_url = ai_cfg.get("base_url") or os.getenv("LLM_API_BASE")
        model = ai_cfg.get("model", "qwen3.8-max")
        # litellm OpenAI-compatible routing
        model_name = f"openai/{model}"
        if base_url:
            os.environ.setdefault("OPENAI_API_BASE", base_url)

        legs_txt = "\n".join(
            f"- {l.action.upper()} {l.qty} {l.ticker} {l.option_type} "
            f"K={l.strike} exp={l.expiration} premium={l.premium:.2f} "
            f"delta={l.delta if l.delta is not None else 'n/a'} "
            f"vol={l.volume} oi={l.open_interest}"
            for l in strategy.legs
        )
        prompt = f"""You are a senior options risk analyst. Review this proposed PAPER trade and decide whether to APPROVE or VETO it. Be conservative about undefined risk, poor liquidity, and weak edge.

UNDERLYING: {strategy.ticker}
STRATEGY: {strategy.name} ({strategy.type})
BIAS: {strategy.bias} (composite score {signal.get('score')}, momentum {signal.get('momentum')})
SENTIMENT: score={signal.get('sentiment', {}).get('score')}, news_count={signal.get('sentiment', {}).get('news_count')}
METRICS: {json.dumps(strategy.metrics)}
LEGS:
{legs_txt}

Respond in strict JSON: {{"approve": true|false, "reasoning": "one paragraph"}}
"""
        resp = litellm.completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=60,
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
        return bool(data.get("approve", True)), str(data.get("reasoning", ""))
    except Exception as e:
        logger.error("ai_review failed (failing open): %s", e)
        return True, f"ai_review error: {e}"
