"""CORAL API Server — FastAPI proxy between CORAL agents and SGLang.

Receives OpenAI-format chat completion requests from CORAL's litellm
gateway, forwards to SGLang for on-policy inference, extracts logprobs,
and creates SLIME Sample objects for RL training.

Reward is deferred: samples are buffered per-agent until CORAL's eval
system produces a score, at which point improvement (score - parent_score)
is assigned as the reward and samples are submitted to the output queue.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import time
from itertools import count
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from slime.utils.processing_utils import load_tokenizer
from slime.utils.types import Sample

logger = logging.getLogger(__name__)

_NON_STANDARD_BODY_KEYS = {"session_id", "session_done", "turn_type"}


def _flatten_message_content(content: Any) -> str:
    """Extract plain text from multimodal content lists."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return " ".join(parts) if parts else ""
    return str(content) if content is not None else ""


def _normalize_messages_for_template(messages: list[dict]) -> list[dict]:
    """Make messages compatible with the chat template.

    - developer -> system (templates only know 'system')
    - multimodal content lists -> plain text strings
    - tool_call arguments: JSON string -> dict (for Jinja2 |items)
    """
    out = []
    for msg in messages:
        m = dict(msg)
        if m.get("role") == "developer":
            m["role"] = "system"
        raw = m.get("content")
        if not isinstance(raw, str) and raw is not None:
            m["content"] = _flatten_message_content(raw)
        if m.get("tool_calls"):
            m["tool_calls"] = [_normalize_tool_call(tc) for tc in m["tool_calls"]]
        out.append(m)
    return out


def _normalize_tool_call(tc: dict) -> dict:
    """Ensure tool_call.function.arguments is a dict so Jinja2 |items works."""
    tc = dict(tc)
    fn = tc.get("function")
    if isinstance(fn, dict):
        fn = dict(fn)
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                fn["arguments"] = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                fn["arguments"] = {}
        tc["function"] = fn
    return tc


def _extract_logprobs_from_chat_response(choice: dict[str, Any]) -> list[float]:
    """Extract per-token logprobs from an SGLang chat completion choice."""
    logprobs_obj = choice.get("logprobs")
    if not isinstance(logprobs_obj, dict):
        return []
    content = logprobs_obj.get("content")
    if not isinstance(content, list):
        return []
    return [float(item.get("logprob", 0.0)) for item in content if isinstance(item, dict)]


def _message_fingerprint(messages: list[dict]) -> str:
    """Create a hash fingerprint from a messages list for cross-service matching.

    Used to correlate requests between the gateway log (which knows agent_id)
    and CoralAPIServer (which needs agent_id). Uses message count + last
    message role and content for robustness against proxy transformations.
    """
    if not messages:
        return ""
    last = messages[-1]
    content = last.get("content", "")
    if isinstance(content, list):
        content = _flatten_message_content(content)
    elif not isinstance(content, str):
        content = str(content) if content is not None else ""
    key = f"{len(messages)}|{last.get('role', '')}|{content}"
    return hashlib.md5(key.encode("utf-8", errors="replace")).hexdigest()


class GatewayLogReader:
    """Reads gateway requests.jsonl to resolve agent IDs by message fingerprint.

    The CORAL gateway identifies agents by API key and logs each request with
    agent_id to requests.jsonl.  Since LiteLLM creates new HTTP requests when
    forwarding (losing custom ASGI headers), this reader provides an
    alternative way for CoralAPIServer to identify agents by matching message
    fingerprints between the log and incoming requests.
    """

    def __init__(self, log_path: str):
        self._log_path = log_path
        self._offset = 0
        self._fp_to_agent: dict[str, str] = {}
        self._lock = threading.Lock()

    def refresh(self) -> None:
        """Read new entries from the gateway log file."""
        try:
            if not os.path.exists(self._log_path):
                return
            with open(self._log_path, "r") as f:
                f.seek(self._offset)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    agent_id = entry.get("agent_id")
                    request = entry.get("request")
                    if agent_id and agent_id != "unknown" and isinstance(request, dict):
                        messages = request.get("messages")
                        if isinstance(messages, list) and messages:
                            fp = _message_fingerprint(messages)
                            with self._lock:
                                self._fp_to_agent[fp] = agent_id
                self._offset = f.tell()
        except OSError as e:
            logger.debug("[Coral] gateway log read error: %s", e)

    def lookup(self, fingerprint: str) -> str | None:
        """Look up agent_id by message fingerprint."""
        with self._lock:
            return self._fp_to_agent.get(fingerprint)


# ---------------------------------------------------------------------------
# Module-level SLIME integration functions
# ---------------------------------------------------------------------------


async def reward_func(args: Any, sample_or_samples: Any, **kwargs: Any) -> dict | list[dict]:
    """SLIME reward function. Reads score from sample.reward dict.

    Registered via ``--custom-rm-path coral_api_server.reward_func``.
    """
    if isinstance(sample_or_samples, list):
        return [
            {"score": s.reward.get("score", 0.0) if isinstance(s.reward, dict) else 0.0}
            for s in sample_or_samples
        ]
    s = sample_or_samples
    return {"score": s.reward.get("score", 0.0) if isinstance(s.reward, dict) else 0.0}


async def generate(
    args: Any,
    sample: Sample,
    sampling_params: dict,
    evaluation: bool = False,
) -> Sample:
    """SLIME generate function for eval rollouts.

    Registered via ``--custom-generate-function-path coral_api_server.generate``.
    """
    tokenizer = load_tokenizer(args.hf_checkpoint, trust_remote_code=True)
    messages = (
        sample.prompt
        if isinstance(sample.prompt, list)
        else [{"role": "user", "content": str(sample.prompt)}]
    )
    input_ids = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
    )
    payload = {
        "input_ids": input_ids,
        "sampling_params": sampling_params,
        "return_logprob": True,
    }
    url = f"http://{args.sglang_router_ip}:{args.sglang_router_port}/generate"
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        output = response.json()

    text = output.get("text", "")
    meta = output.get("meta_info", {})
    pairs = meta.get("output_token_logprobs", [])
    if isinstance(pairs, list) and pairs:
        token_ids = [int(p[1]) for p in pairs if isinstance(p, (list, tuple)) and len(p) >= 2]
        logprobs = [float(p[0]) for p in pairs if isinstance(p, (list, tuple)) and len(p) >= 2]
    else:
        token_ids = tokenizer(text, add_special_tokens=False)["input_ids"]
        logprobs = [0.0] * len(token_ids)

    sample.tokens = input_ids + token_ids
    sample.response = text
    sample.response_length = len(token_ids)
    sample.rollout_log_probs = logprobs
    sample.loss_mask = [1] * len(token_ids)
    sample.status = Sample.Status.COMPLETED
    return sample


# ---------------------------------------------------------------------------
# CoralAPIServer
# ---------------------------------------------------------------------------


class CoralAPIServer:
    """Proxy between CORAL agents and SGLang for RL training data collection.

    CORAL agents connect via the litellm gateway (which converts Anthropic
    Messages API to OpenAI Chat Completions). This server receives the
    already-converted OpenAI format, forwards to SGLang, extracts logprobs,
    and creates SLIME ``Sample`` objects.

    Unlike OpenClaw's PRM-based per-turn scoring, reward assignment is
    deferred until CORAL's eval system produces a score. Samples are
    buffered per-agent and submitted to the output queue when
    ``report_eval_score()`` is called.
    """

    def __init__(
        self,
        args: Any,
        output_queue: queue.Queue,
        submission_enabled: threading.Event,
    ):
        self.args = args
        self.output_queue = output_queue
        self.submission_enabled = submission_enabled
        self.tokenizer = load_tokenizer(args.hf_checkpoint, trust_remote_code=True)

        self.sglang_chat_url = (
            f"http://{args.sglang_router_ip}:{args.sglang_router_port}/v1/chat/completions"
        )
        self.sglang_health_url = f"http://{args.sglang_router_ip}:{args.sglang_router_port}/health"

        self.expected_api_key = os.getenv("SGLANG_API_KEY", "")
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "30000"))
        self.served_model_name = os.getenv("SERVED_MODEL_NAME", "qwen3-30b-a3b")

        # Counters
        self._index_counter = count(0)
        self._group_counter = count(0)
        self._turn_counts: dict[str, int] = {}  # agent_id -> turn count

        # Per-agent sample buffer (deferred reward assignment)
        self._pending_samples: dict[str, list[Sample]] = {}
        self._pending_lock = threading.Lock()

        # Gateway log reader for resolving agent IDs via message fingerprints.
        # The gateway logs each request with agent_id to requests.jsonl;
        # we match messages to recover agent_id that LiteLLM doesn't forward.
        self._gateway_reader = None
        self._sample_fingerprints: dict[int, str] = {}  # sample.index -> fingerprint

        # Eval score tracking for metrics
        self._eval_scores: list[float] = []
        self._eval_scores_lock = threading.Lock()

        # Record file for session logging
        self._record_enabled = os.getenv("CORAL_RECORD_ENABLED", "0") == "1"
        self._record_file = os.getenv("CORAL_RECORD_FILE", "")
        if self._record_enabled and self._record_file:
            os.makedirs(os.path.dirname(self._record_file), exist_ok=True)
            open(self._record_file, "w").close()
            logger.info("[Coral] record file initialized: %s", self._record_file)

        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self.app = self._build_app()

    # ------------------------------------------------------------------ app

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="CORAL SLIME Proxy")
        app.state.owner = self

        @app.get("/healthz")
        async def healthz():
            return {"ok": True}

        @app.get("/v1/models")
        async def list_models():
            return {
                "object": "list",
                "data": [
                    {
                        "id": self.served_model_name,
                        "object": "model",
                        "owned_by": "coral",
                    }
                ],
            }

        @app.post("/v1/chat/completions")
        async def chat_completions(
            request: Request,
            authorization: str | None = Header(default=None),
            x_coral_agent_id: str | None = Header(default=None),
        ):
            owner: CoralAPIServer = request.app.state.owner
            await owner._check_auth(authorization)

            body = await request.json()
            agent_id = x_coral_agent_id or body.pop("agent_id", None) or "unknown"
            stream = bool(body.get("stream", False))

            if stream:
                return await owner._handle_streaming_request(body, agent_id=agent_id)

            result = await owner._handle_request(body, agent_id=agent_id)
            return JSONResponse(content=result["response"])

        return app

    async def _check_auth(self, authorization: str | None) -> None:
        if not self.expected_api_key:
            return
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        token = authorization.split(" ", 1)[1].strip()
        if token != self.expected_api_key:
            raise HTTPException(status_code=401, detail="invalid api key")

    # ---------------------------------------------------- request handling

    async def _handle_request(
        self,
        body: dict[str, Any],
        agent_id: str,
    ) -> dict[str, Any]:
        """Forward non-streaming request to SGLang, extract logprobs, create Sample."""
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(
                status_code=400,
                detail="messages must be a non-empty list",
            )

        tools = body.get("tools")

        # Prepare forwarding body
        forward_body = {k: v for k, v in body.items() if k not in _NON_STANDARD_BODY_KEYS}
        forward_body["stream"] = False
        forward_body.pop("stream_options", None)
        forward_body["logprobs"] = True
        forward_body["top_logprobs"] = 1
        if "model" not in forward_body:
            forward_body["model"] = self.served_model_name

        # Forward to SGLang
        async with httpx.AsyncClient(timeout=None) as client:
            sglang_resp = await client.post(self.sglang_chat_url, json=forward_body)
            if sglang_resp.status_code != 200:
                logger.error(
                    "[Coral] SGLang returned %d: %s",
                    sglang_resp.status_code,
                    sglang_resp.text[:1000],
                )
                sglang_resp.raise_for_status()
            try:
                output = sglang_resp.json()
            except Exception:
                logger.error("[Coral] SGLang non-JSON body: %s", sglang_resp.text[:1000])
                raise

        choice = output.get("choices", [{}])[0]
        assistant_msg = choice.get("message", {})
        response_logprobs = _extract_logprobs_from_chat_response(choice)

        self._create_training_sample(
            agent_id=agent_id,
            messages=messages,
            tools=tools,
            assistant_msg=assistant_msg,
            response_logprobs=response_logprobs,
        )

        return {"response": output}

    async def _handle_streaming_request(
        self,
        body: dict[str, Any],
        agent_id: str,
    ) -> StreamingResponse:
        """Forward streaming request to SGLang, pass SSE chunks through, collect sample data."""
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(
                status_code=400,
                detail="messages must be a non-empty list",
            )

        tools = body.get("tools")

        forward_body = {k: v for k, v in body.items() if k not in _NON_STANDARD_BODY_KEYS}
        forward_body["stream"] = True
        forward_body["logprobs"] = True
        forward_body["top_logprobs"] = 1
        if "model" not in forward_body:
            forward_body["model"] = self.served_model_name

        # Mutable containers for data collected during streaming
        collected = {
            "content": "",
            "reasoning": "",
            "tool_calls": [],
            "logprobs": [],
        }

        async def generate():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", self.sglang_chat_url, json=forward_body
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        logger.error(
                            "[Coral] SGLang stream error %d: %s",
                            resp.status_code,
                            error_body.decode(errors="replace")[:1000],
                        )
                        err = {
                            "error": {
                                "message": f"SGLang returned {resp.status_code}",
                                "type": "upstream_error",
                            }
                        }
                        yield f"data: {json.dumps(err)}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    async for raw_line in resp.aiter_lines():
                        if not raw_line.startswith("data: "):
                            continue

                        data_str = raw_line[6:].strip()
                        if data_str == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break

                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            yield f"data: {data_str}\n\n"
                            continue

                        # Collect data for training sample
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})

                            if delta.get("content"):
                                collected["content"] += delta["content"]
                            if delta.get("reasoning_content"):
                                collected["reasoning"] += delta["reasoning_content"]

                            if delta.get("tool_calls"):
                                for tc in delta["tool_calls"]:
                                    idx = tc.get("index", 0)
                                    while len(collected["tool_calls"]) <= idx:
                                        collected["tool_calls"].append(
                                            {
                                                "id": "",
                                                "type": "function",
                                                "function": {
                                                    "name": "",
                                                    "arguments": "",
                                                },
                                            }
                                        )
                                    if tc.get("id"):
                                        collected["tool_calls"][idx]["id"] = tc["id"]
                                    if tc.get("type"):
                                        collected["tool_calls"][idx]["type"] = tc["type"]
                                    fn = tc.get("function", {})
                                    if fn.get("name"):
                                        collected["tool_calls"][idx]["function"][
                                            "name"
                                        ] = fn["name"]
                                    if "arguments" in fn:
                                        collected["tool_calls"][idx]["function"][
                                            "arguments"
                                        ] += fn["arguments"]

                            lp = choices[0].get("logprobs")
                            if isinstance(lp, dict):
                                content_lp = lp.get("content")
                                if isinstance(content_lp, list):
                                    for item in content_lp:
                                        if isinstance(item, dict):
                                            collected["logprobs"].append(
                                                float(item.get("logprob", 0.0))
                                            )

                        # Forward chunk as-is to client
                        yield f"data: {data_str}\n\n"

            # Stream complete — create training sample
            assistant_msg = {
                "role": "assistant",
                "content": collected["content"] or "",
            }
            if collected["reasoning"]:
                assistant_msg["reasoning_content"] = collected["reasoning"]
            if collected["tool_calls"]:
                assistant_msg["tool_calls"] = collected["tool_calls"]

            self._create_training_sample(
                agent_id=agent_id,
                messages=messages,
                tools=tools,
                assistant_msg=assistant_msg,
                response_logprobs=collected["logprobs"],
            )

        return StreamingResponse(generate(), media_type="text/event-stream")

    def _create_training_sample(
        self,
        agent_id: str,
        messages: list[dict],
        tools: list[dict] | None,
        assistant_msg: dict,
        response_logprobs: list[float],
    ) -> None:
        """Create and buffer a training Sample from a completed response."""
        # Reconcile previously-unknown samples using gateway log entries that
        # have appeared since the last call (the gateway writes its log entry
        # after the full response cycle, so previous requests' entries are
        # available by the time the next request arrives).
        if agent_id == "unknown":
            self._reconcile_unknown_samples()

        tool_calls = assistant_msg.get("tool_calls") or []
        content = assistant_msg.get("content") or ""
        reasoning = assistant_msg.get("reasoning_content") or ""

        logger.info(
            "[Coral] agent=%s prompt_msgs=%d thinking=%d response=%d tool_calls=%d",
            agent_id,
            len(messages),
            len(reasoning),
            len(content),
            len(tool_calls),
        )

        response_msg = dict(assistant_msg)
        if response_msg.get("content") is None:
            response_msg["content"] = ""

        norm_msgs = _normalize_messages_for_template(messages)
        norm_resp = _normalize_messages_for_template([response_msg])[0]
        full_norm = norm_msgs + [norm_resp]

        prompt_text = self.tokenizer.apply_chat_template(
            norm_msgs,
            tools=tools,
            tokenize=False,
            add_generation_prompt=True,
        )
        full_text = self.tokenizer.apply_chat_template(
            full_norm,
            tools=tools,
            tokenize=False,
            add_generation_prompt=False,
        )

        if full_text.startswith(prompt_text):
            response_text = full_text[len(prompt_text):]
        else:
            logger.warning(
                "[Coral] prompt_text not a prefix of full_text, using full_text as response",
            )
            response_text = full_text

        prompt_ids = self.tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        response_ids = self.tokenizer(response_text, add_special_tokens=False)["input_ids"]

        if not response_ids and not response_text.strip():
            logger.info("[Coral] agent=%s empty response, skipping sample", agent_id)
            return

        # Align logprobs length with response tokens
        if len(response_logprobs) > len(response_ids):
            response_logprobs = response_logprobs[: len(response_ids)]
        elif len(response_logprobs) < len(response_ids):
            response_logprobs = response_logprobs + [0.0] * (
                len(response_ids) - len(response_logprobs)
            )

        self._turn_counts[agent_id] = self._turn_counts.get(agent_id, 0) + 1
        turn_num = self._turn_counts[agent_id]

        sample = Sample()
        sample.prompt = prompt_text
        sample.response = response_text
        sample.tokens = prompt_ids + response_ids
        sample.response_length = len(response_ids)
        sample.loss_mask = [1] * len(response_ids)
        sample.rollout_log_probs = response_logprobs
        sample.status = Sample.Status.COMPLETED
        sample.index = next(self._index_counter)
        sample.group_index = next(self._group_counter)
        sample.reward = {"score": 0.0}

        logger.info(
            "[Coral] buffered sample agent=%s turn=%d index=%d prompt_tokens=%d response_tokens=%d",
            agent_id,
            turn_num,
            sample.index,
            len(prompt_ids),
            len(response_ids),
        )

        with self._pending_lock:
            self._pending_samples.setdefault(agent_id, []).append(sample)

        # Store fingerprint for later reconciliation via gateway log
        if self._gateway_reader:
            fp = _message_fingerprint(messages)
            self._sample_fingerprints[sample.index] = fp

        self._write_record(agent_id, turn_num, messages, prompt_text, response_text, tool_calls)

    # ---------------------------------------------------- gateway log reconciliation

    def _reconcile_unknown_samples(self) -> None:
        """Re-key samples from 'unknown' to correct agent using gateway log.

        The gateway logs each request with agent_id after the response cycle.
        This method reads new log entries, matches them to buffered samples by
        message fingerprint, and moves samples to the correct agent_id bucket.
        """
        if not self._gateway_reader:
            return
        self._gateway_reader.refresh()

        with self._pending_lock:
            unknown_samples = self._pending_samples.get("unknown")
            if not unknown_samples:
                return

            remaining = []
            for sample in unknown_samples:
                fp = self._sample_fingerprints.get(sample.index)
                if fp:
                    resolved = self._gateway_reader.lookup(fp)
                    if resolved and resolved != "unknown":
                        self._pending_samples.setdefault(resolved, []).append(sample)
                        logger.info(
                            "[Coral] reconciled sample %d -> agent=%s",
                            sample.index,
                            resolved,
                        )
                        continue
                remaining.append(sample)

            if remaining:
                self._pending_samples["unknown"] = remaining
            else:
                self._pending_samples.pop("unknown", None)

    # ---------------------------------------------------- reward integration

    def report_eval_score(
        self,
        agent_id: str,
        score: float,
        parent_score: float,
    ) -> None:
        """Called by the eval monitor when a CORAL eval attempt completes.

        Computes improvement = score - parent_score, assigns it as the
        reward to all buffered samples for this agent, and submits them
        to the output queue.
        """
        # Final reconciliation: re-key any remaining "unknown" samples
        # using gateway log entries that have accumulated.
        self._reconcile_unknown_samples()

        improvement = score - parent_score
        logger.info(
            "[Coral] eval: agent=%s score=%.4f parent=%.4f improvement=%.4f",
            agent_id,
            score,
            parent_score,
            improvement,
        )

        with self._eval_scores_lock:
            self._eval_scores.append(improvement)

        with self._pending_lock:
            samples = self._pending_samples.pop(agent_id, [])
            # Fallback: when gateway is disabled, OpenCode doesn't send
            # X-Coral-Agent-Id, so samples are buffered under "unknown".
            if not samples and agent_id != "unknown":
                samples = self._pending_samples.pop("unknown", [])

        if not samples:
            logger.info("[Coral] no pending samples for agent=%s, reward discarded", agent_id)
            return

        # Clean up fingerprints for submitted samples
        for s in samples:
            self._sample_fingerprints.pop(s.index, None)

        for s in samples:
            s.reward = {"score": improvement}
            # Exclude from loss if improvement is exactly 0 (no change)
            if improvement == 0.0:
                s.loss_mask = [0] * s.response_length

        # Submit to output queue
        for s in samples:
            self.output_queue.put((s.group_index, [s]))

        logger.info(
            "[Coral] submitted %d samples for agent=%s with reward=%.4f",
            len(samples),
            agent_id,
            improvement,
        )

    def flush_agent(self, agent_id: str) -> None:
        """Submit any remaining buffered samples for an agent with reward=0.

        Called when an agent dies or session ends without a final eval.
        """
        self._reconcile_unknown_samples()

        with self._pending_lock:
            samples = self._pending_samples.pop(agent_id, [])

        if not samples:
            return

        for s in samples:
            self._sample_fingerprints.pop(s.index, None)
            s.reward = {"score": 0.0}
            s.loss_mask = [0] * s.response_length  # Don't train on unrewarded samples

        for s in samples:
            self.output_queue.put((s.group_index, [s]))

        logger.info(
            "[Coral] flushed %d unrewarded samples for agent=%s",
            len(samples),
            agent_id,
        )

    # ---------------------------------------------------- eval score metrics

    def drain_eval_scores(self) -> list[float]:
        with self._eval_scores_lock:
            scores = list(self._eval_scores)
            self._eval_scores.clear()
            return scores

    def reset_eval_scores(self) -> None:
        with self._eval_scores_lock:
            self._eval_scores.clear()

    # ---------------------------------------------------- record file

    def _write_record(
        self,
        agent_id: str,
        turn_num: int,
        messages: list,
        prompt_text: str,
        response_text: str,
        tool_calls: list,
    ) -> None:
        if not self._record_enabled or not self._record_file:
            return
        rec = {
            "agent_id": agent_id,
            "turn": turn_num,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompt_text": prompt_text[:500],  # Truncate for readability
            "response_text": response_text[:500],
            "tool_calls": tool_calls[:3] if tool_calls else None,
        }
        try:
            with open(self._record_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("[Coral] failed to write record: %s", e)

    def purge_record_files(self) -> None:
        """Clear record files. Called at pause boundaries."""
        if self._record_file:
            try:
                open(self._record_file, "w").close()
            except OSError as e:
                logger.warning("[Coral] failed to purge record file: %s", e)

    # ----------------------------------------------------------- streaming
    # (streaming is handled by _handle_streaming_request above)

    # ------------------------------------------------------------- lifecycle

    def set_gateway_log(self, log_path: str) -> None:
        """Configure gateway log reader for agent ID reconciliation.

        Called after ``coral start`` creates the run directory, since the
        log path isn't known at CoralAPIServer init time.
        """
        if log_path and not self._gateway_reader:
            self._gateway_reader = GatewayLogReader(log_path)
            logger.info("[Coral] gateway log reader configured: %s", log_path)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        self._server = uvicorn.Server(config=config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        # Wait for SGLang readiness in background
        self._readiness_thread = threading.Thread(
            target=self._wait_for_sglang_ready,
            daemon=True,
        )
        self._readiness_thread.start()

    def _wait_for_sglang_ready(self) -> None:
        while True:
            try:
                r = httpx.get(self.sglang_health_url, timeout=5)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(3)
        logger.info("[Coral] SGLang policy server ready")
        time.sleep(5)
        banner = (
            f"\n{'=' * 70}\n"
            f"  [Coral] API server ready\n"
            f"  proxy {self.host}:{self.port} -> SGLang "
            f"{self.args.sglang_router_ip}:{self.args.sglang_router_port}\n"
            f"{'=' * 70}\n"
        )
        logger.info(banner)

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
