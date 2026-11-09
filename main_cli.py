#!/usr/bin/env python3
"""
Universal Code AI
Training (Bot) → Independent (No modules)

Usage:
  python main.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.knowledge_db import KnowledgeDB
from core.module_manager import ModuleManager
from core.training_manager import TrainingManager
from core.code_generator import CodeGenerator
from core.local_model import LocalModel
from core.model_manager import ModelManager
from core.project_generator import ProjectGenerator
from core.code_validator import CodeValidator
from config import PROJECTS_DIR


def banner():
    print("""
╔══════════════════════════════════════════════════════╗
║   Universal Code AI                                  ║
║   Training Mode → Independent Mode                   ║
║   Bot se seekho → Modules se free ho jao             ║
╚══════════════════════════════════════════════════════╝
""")


def help_text():
    print("""
Commands:
  gen <request>              Generate code
  gen <lang> : <request>     Force language
  progress                   Training / knowledge status
  model-status               Check local model server
  model-info                 Show phone RAM/storage and model status
  model-start [GGUF-path]    Start local llama.cpp coding model
  model-stop                 Stop managed local model server
  save-project <name>        Save last generated multi-file output as ZIP
  validate <project-folder>  Run supported static syntax checks
  learn <url>                Save public documentation page locally
  online-off                 Disable online learning (local model remains)
  online-remove              Disable and mark online module removed
  online-purge                Delete online-learning source after disabling it
  online-on                  Enable online learning
  add                        Manually add knowledge
  search <query>             Search local knowledge
  help                       This help
  exit                       Quit

Examples:
  gen python quicksort implementation
  gen create a rate limiter in go
  gen kotlin : android login with room database
  progress
""")


def main():
    banner()

    db = KnowledgeDB()
    trainer = TrainingManager(db)
    generator = CodeGenerator(db)
    modules = ModuleManager(db)
    model = LocalModel()
    model_manager = ModelManager()
    project_writer = ProjectGenerator(PROJECTS_DIR)
    validator = CodeValidator()
    last_generation = {"content": ""}
    print("Mode: LOCAL MODEL + OPTIONAL ONLINE DOCUMENTATION")
    print("No API key is configured or required. Start a local llama.cpp server for generation.")
    print("Type 'help' for commands.\n")

    while True:
        try:
            inp = input(">>> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not inp:
            continue

        low = inp.lower()

        if low in ("exit", "quit", "q"):
            print("Bye!")
            break

        if low == "help":
            help_text()
            continue

        if low == "model-status":
            print(model.health())
            print(model.list_models())
            continue

        if low == "model-info":
            print(model_manager.device_info())
            continue

        if low == "model-stop":
            print(model_manager.stop())
            continue

        if low == "model-start" or low.startswith("model-start "):
            parts = inp.split(maxsplit=1)
            manager = ModelManager(parts[1].strip()) if len(parts) > 1 else model_manager
            print(manager.start(context=2048))
            continue

        if low.startswith("save-project "):
            name = inp.split(maxsplit=1)[1].strip()
            result = project_writer.save(last_generation.get("content", ""), name)
            print(result)
            continue

        if low.startswith("validate "):
            folder = inp.split(maxsplit=1)[1].strip()
            print(validator.validate_project(folder))
            continue

        if low == "progress":
            print(trainer.get_report())
            continue

        if low.startswith("learn "):
            url = inp[6:].strip()
            print(generator.learn_url(url))
            continue

        if low == "online-off":
            modules.disable_online_learning()
            print("Online learning disabled. Local model and database remain available.")
            continue

        if low == "online-remove":
            modules.remove_online_learning()
            print("Online learning disabled and marked removed. Local model and database remain.")
            print("Use online-purge only if you also want to delete its source file.")
            continue

        if low == "online-purge":
            modules.remove_online_learning()
            source = Path(__file__).parent / "core" / "online_learning.py"
            if source.exists():
                source.unlink()
                print("Online learning source deleted. Local model and database remain.")
            else:
                print("Online learning source is already absent. Local model and database remain.")
            continue

        if low == "online-on":
            if db.get_state("online_learning_removed", "0") == "1":
                print("Online module is marked removed. Restore core/online_learning.py from backup before enabling it.")
            else:
                modules.enable_online_learning()
                print("Online documentation learning enabled.")
            continue

        if low.startswith("search "):
            q = inp[7:].strip()
            results = db.search(query=q, limit=6)
            if not results:
                print("No results.")
            else:
                for r in results:
                    print(f"\n[{r['id']}] {r['language']} score={r['verification_score']:.2f}")
                    print(r.get("title", "")[:70])
                    print(r["code"][:180] + "...")
            continue

        if low == "add":
            print("Manual knowledge add")
            lang = input("Language: ").strip().lower()
            title = input("Title: ").strip()
            print("Paste code (empty line to finish):")
            lines = []
            try:
                while True:
                    line = input()
                    if not line.strip() and lines:
                        break
                    lines.append(line)
            except EOFError:
                pass
            code = "\n".join(lines)
            if code.strip():
                res = trainer.add_manual(lang, code, title=title)
                print(res)
            continue

        if low.startswith("gen ") or low.startswith("generate "):
            request = inp.split(maxsplit=1)[1].strip()
            language = None

            if ":" in request:
                maybe, rest = request.split(":", 1)
                maybe = maybe.strip().lower()
                if maybe in ["python","java","kotlin","c","cpp","csharp","javascript","typescript",
                             "php","go","rust","ruby","swift","dart","html","css","sql","bash","lua","haskell",
                             "js","ts","py","c++","c#"]:
                    language = maybe
                    request = rest.strip()

            print(f"\n⏳ Generating... (lang={language or 'auto'})")
            result = generator.generate(request, language=language)
            last_generation["content"] = result.get("content", "")

            mode = result.get("mode", "unknown").upper()
            print(f"\n── Mode: {mode} | Lang: {result.get('language', '?')} ──\n")
            print(result.get("content", "No output"))
            print("\n" + "─" * 50)

            if result.get("knowledge_id"):
                print(f"💾 Saved to knowledge: {result['knowledge_id']}")

            continue

        print("Unknown command. Type 'help'.")


if __name__ == "__main__":
    main()
