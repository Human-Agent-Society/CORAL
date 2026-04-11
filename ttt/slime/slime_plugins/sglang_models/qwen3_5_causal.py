import os

if os.environ.get("SLIME_ENABLE_QWEN35_SGLANG_PATCH") == "1":
    from slime.backends.sglang_utils.qwen3_5 import patch_sglang_qwen35
    patch_sglang_qwen35()

from sglang.srt.models.qwen3_5 import Qwen3_5ForCausalLM

EntryClass = [Qwen3_5ForCausalLM]
