from pathlib import Path


def test_operator_has_no_provider_specific_imports():
    source = (Path(__file__).parents[1] / "slipstream" / "loop" / "operator.py").read_text(encoding="utf-8")
    forbidden = [
        "backends.claude_code",
        "backends.pi",
        "backends.openai",
        "ClaudeCodeBackend",
        "PiBackend",
        "OpenAIBackend",
    ]
    for token in forbidden:
        assert token not in source
