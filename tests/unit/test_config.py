import os
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from src.config import PROJECT_ROOT, Settings


class ConfigTest(unittest.TestCase):
    def test_default_paths_are_under_project_root(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "dummy"}, clear=False):
            config = Settings(_env_file=None)

        self.assertEqual(config.data_dir, PROJECT_ROOT / "data")
        self.assertEqual(config.documents_dir, PROJECT_ROOT / "data" / "documents")
        self.assertEqual(config.database_path, PROJECT_ROOT / "data" / "local_kb.db")
        self.assertEqual(config.chroma_path, PROJECT_ROOT / "data" / "chroma")

    def test_missing_api_key_raises_validation_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_environment_override(self):
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "dummy",
                "DEEPSEEK_MODEL": "custom-model",
                "MIN_SIMILARITY": "0.75",
            },
            clear=False,
        ):
            config = Settings(_env_file=None)

        self.assertEqual(config.deepseek_model, "custom-model")
        self.assertEqual(config.min_similarity, 0.75)


if __name__ == "__main__":
    unittest.main()
