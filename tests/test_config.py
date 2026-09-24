import pytest

from academic_pdf_translator.config import Settings


def test_dotenv_uses_working_directory_without_overriding_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Register an undo even if the variable was originally absent: dotenv writes
    # directly into os.environ and must not leak into later tests.
    monkeypatch.setenv("APT_MODEL", "temporary")
    monkeypatch.delenv("APT_MODEL")
    monkeypatch.setenv("APT_API_KEY", "environment-wins")
    (tmp_path / ".env").write_text(
        "APT_MODEL=local-test-model\nAPT_API_KEY=file-value\n", encoding="utf-8"
    )
    settings = Settings.from_env()
    assert settings.model == "local-test-model"
    assert settings.api_key == "environment-wins"


@pytest.mark.parametrize(
    "config",
    [
        {"timeout": float("nan")},
        {"timeout": 0},
        {"max_retries": 100},
        {"context_chars": -1},
        {"max_current_chars": 0},
    ],
)
def test_invalid_budgets_rejected(config):
    with pytest.raises(ValueError):
        Settings(**config)
