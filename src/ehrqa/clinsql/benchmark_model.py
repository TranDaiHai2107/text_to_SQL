"""Model identity shared by CLINSQL inference entry points."""

BENCHMARK_LLM = 'gpt-5-mini-2025-08-07'


class ModelMismatch(PermissionError):
    def __init__(self):
        super().__init__('MODEL_MISMATCH')


def require_benchmark_model(model_id):
    if model_id != BENCHMARK_LLM:
        raise ModelMismatch()
