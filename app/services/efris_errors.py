from datetime import datetime, timezone


class EfrisErrorService:
    def __init__(self, repository):
        self.repository = repository

    def dashboard(self, minutes=60):
        summary = dict(self.repository.summary(minutes))
        summary["refreshed_at"] = datetime.now(timezone.utc).isoformat()
        return {
            "summary": summary,
            "top_codes": self.repository.top_codes(minutes),
            "top_taxpayers": self.repository.top_taxpayers(minutes),
            "trend": self.repository.trend(minutes),
            "recent": self.repository.recent(minutes),
        }
