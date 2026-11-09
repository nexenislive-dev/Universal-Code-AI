"""Controls optional online-learning features without touching local model/data."""
class ModuleManager:
    def __init__(self, db):
        self.db = db

    def online_enabled(self) -> bool:
        return self.db.get_state("online_learning_enabled", "1") == "1"

    def disable_online_learning(self):
        self.db.set_state("online_learning_enabled", "0")
        return True

    def enable_online_learning(self):
        self.db.set_state("online_learning_enabled", "1")
        return True

    def remove_online_learning(self):
        # Logical removal: source code remains installed until user manually deletes it.
        # This prevents accidental loss of local model/database functionality.
        self.disable_online_learning()
        self.db.set_state("online_learning_removed", "1")
        return True
