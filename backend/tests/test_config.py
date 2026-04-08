import logging
from unittest.mock import patch

from backend.config import settings as config


class TestValidateConfig:
    def test_warns_when_anthropic_api_key_missing(self, caplog):
        with patch.object(config, "_WARNED_VARS", {"ANTHROPIC_API_KEY": ""}):
            with caplog.at_level(logging.WARNING):
                config.validate_config()
            assert "ANTHROPIC_API_KEY" in caplog.text

    def test_no_warning_when_all_vars_set(self, caplog):
        with patch.object(config, "_WARNED_VARS", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with caplog.at_level(logging.WARNING):
                config.validate_config()
            assert caplog.text == ""

    def test_lists_all_missing_vars_in_warning(self, caplog):
        with patch.object(config, "_WARNED_VARS", {"A": "", "B": "", "C": "ok"}):
            with caplog.at_level(logging.WARNING):
                config.validate_config()
            assert "A" in caplog.text
            assert "B" in caplog.text
            assert "C" not in caplog.text
