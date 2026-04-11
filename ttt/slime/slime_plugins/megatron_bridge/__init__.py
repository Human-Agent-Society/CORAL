# rope_theta_compat: monkey-patch Qwen3Config for transformers>=5.0
try:
    from transformers.models.qwen3.configuration_qwen3 import Qwen3Config as _Qwen3Config

    _qwen3_orig_init = _Qwen3Config.__init__

    def _qwen3_patched_init(self, *args, **kwargs):
        _rope_theta = kwargs.pop("rope_theta", None)
        _qwen3_orig_init(self, *args, **kwargs)
        if not hasattr(self, "rope_theta") or self.rope_theta is None:
            self.rope_theta = _rope_theta if _rope_theta is not None else 1000000

    _Qwen3Config.__init__ = _qwen3_patched_init
except Exception:
    pass

try:
    import slime_plugins.megatron_bridge.qwen3_5  # noqa: F401  # register Qwen3.5 bridge
except (ImportError, ModuleNotFoundError):
    pass  # Qwen3.5 requires transformers with qwen3_5 model support
