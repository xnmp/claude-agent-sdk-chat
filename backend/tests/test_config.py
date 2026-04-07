import pytest
from unittest.mock import patch

from backend import config


class TestValidateConfig:
    def test_raises_when_anthropic_api_key_missing(self):
        with patch.object(config, "_REQUIRED_VARS", {"ANTHROPIC_API_KEY": ""}):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                config.validate_config()

    def test_passes_when_all_required_vars_set(self):
        with patch.object(config, "_REQUIRED_VARS", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            config.validate_config()  # should not raise

    def test_lists_all_missing_vars_in_error(self):
        with patch.object(config, "_REQUIRED_VARS", {"A": "", "B": "", "C": "ok"}):
            with pytest.raises(RuntimeError, match="A, B"):
                config.validate_config()
