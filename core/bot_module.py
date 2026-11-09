"""Legacy API module intentionally disabled.
Universal Code AI now uses a local llama.cpp model and does not require API keys.
"""
class BotModule:
    def is_available(self):
        return False

    def generate(self, *args, **kwargs):
        return {"success": False, "content": "", "error": "Legacy API module disabled; use LocalModel/llama.cpp instead."}
