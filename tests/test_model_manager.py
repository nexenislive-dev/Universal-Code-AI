import tempfile
import unittest
from pathlib import Path
from core.model_manager import ModelManager

class ModelManagerTests(unittest.TestCase):
    def test_device_info_is_safe_without_model(self):
        with tempfile.TemporaryDirectory() as td:
            manager = ModelManager(Path(td) / 'missing.gguf')
            info = manager.device_info()
            self.assertFalse(info['model_exists'])
            self.assertIn('storage_free_gb', info)
            self.assertIn('server_available', info)

    def test_start_reports_missing_binary_or_model(self):
        with tempfile.TemporaryDirectory() as td:
            manager = ModelManager(Path(td) / 'missing.gguf')
            result = manager.start(wait_seconds=1)
            self.assertFalse(result['success'])
            self.assertTrue('not found' in result['error'].lower())

if __name__ == '__main__':
    unittest.main()
