import tempfile
import unittest
from pathlib import Path
from core.project_generator import ProjectGenerator
from core.code_validator import CodeValidator
from core.knowledge_db import KnowledgeDB
from core.module_manager import ModuleManager

class CoreTests(unittest.TestCase):
    def test_project_export_and_traversal_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            pg = ProjectGenerator(Path(tmp) / "projects")
            text = """A project\n```file:src/main.py\nprint('ok')\n```\n```file:../escape.py\nBAD\n```"""
            result = pg.save(text, "demo")
            self.assertTrue(result["success"])
            self.assertEqual(result["files"], ["src/main.py"])
            self.assertTrue(Path(result["zip_path"]).exists())
            self.assertFalse((Path(tmp) / "escape.py").exists())

    def test_python_and_json_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.py").write_text("print('hello')\n")
            (root / "bad.py").write_text("def broken(:\n")
            (root / "data.json").write_text('{"ok": true}')
            report = CodeValidator().validate_project(root)
            self.assertEqual(report["checked"], 3)
            self.assertEqual(report["failed"], 1)

    def test_online_toggle_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = KnowledgeDB(Path(tmp) / "test.db")
            mm = ModuleManager(db)
            self.assertTrue(mm.online_enabled())
            mm.disable_online_learning()
            self.assertFalse(mm.online_enabled())
            mm.enable_online_learning()
            self.assertTrue(mm.online_enabled())

if __name__ == "__main__":
    unittest.main()
