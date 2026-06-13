from __future__ import annotations

import unittest

from spam_filter.config import DEFAULT_CLASSIFICATION_PROMPT, get_settings


class ConfigPromptTests(unittest.TestCase):
    def test_default_classification_prompt_is_used_when_env_missing(self) -> None:
        settings = get_settings()

        self.assertTrue(settings.classification_prompt)

    def test_default_prompt_mentions_required_labels(self) -> None:
        self.assertIn("legitimate provider login-code", DEFAULT_CLASSIFICATION_PROMPT)
        self.assertIn("spam_harmful", DEFAULT_CLASSIFICATION_PROMPT)
        self.assertIn("junk_keep", DEFAULT_CLASSIFICATION_PROMPT)


if __name__ == "__main__":
    unittest.main()
