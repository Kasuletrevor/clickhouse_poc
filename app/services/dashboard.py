from datetime import datetime, timezone


class DashboardService:
    def __init__(self, repository):
        self.repository = repository

    def summary(self):
        data = dict(self.repository.summary())
        data["refreshed_at"] = datetime.now(timezone.utc).isoformat()
        return data

    def payments_by_station(self):
        return self.repository.payments_by_station()

    def status_summary(self):
        by_status = {row["status"]: row for row in self.repository.status_summary()}
        result = []
        for status in ("SUCCESSFUL", "PENDING", "REVERSED"):
            row = by_status.get(status, {})
            result.append(
                {
                    "status": status,
                    "payment_count": int(row.get("payment_count", 0) or 0),
                    "amount": row.get("amount", 0) or 0,
                }
            )
        return result

    def recent_activity(self):
        station_names = self.repository.station_name_map()
        activity = []

        for event in self.repository.recent_taxpayer_events():
            translated = self._translate_taxpayer_event(event, station_names)
            if translated is not None:
                activity.append(translated)

        return {
            "recent_payments": self.repository.recent_payments(),
            "recent_taxpayer_activity": activity,
        }

    @staticmethod
    def _station_label(station_id, station_names):
        if not station_id:
            return "Unassigned"
        return station_names.get(station_id, station_id)

    def _translate_taxpayer_event(self, event, station_names):
        taxpayer_id = event.get("taxpayer_id")
        taxpayer_name = event.get("taxpayer_name") or taxpayer_id
        operation = (event.get("dbz_op") or "").lower()
        previous_name = event.get("previous_taxpayer_name") or ""
        previous_type = event.get("previous_taxpayer_type") or ""
        previous_station = event.get("previous_station_id") or ""
        station_id = event.get("station_id") or ""
        taxpayer_type = event.get("taxpayer_type") or ""

        base = {
            "taxpayer_id": taxpayer_id,
            "taxpayer_name": taxpayer_name,
            "occurred_at": event.get("source_commit_time"),
        }

        if operation == "c":
            base.update(
                {
                    "action": "Taxpayer created",
                    "message": taxpayer_name,
                }
            )
            return base

        if operation != "u":
            return None

        if previous_station and previous_station != station_id:
            old_station = self._station_label(previous_station, station_names)
            new_station = self._station_label(station_id, station_names)
            base.update(
                {
                    "action": "Station changed",
                    "message": "{} → {}".format(old_station, new_station),
                    "previous_station": old_station,
                    "station": new_station,
                }
            )
            return base

        changed = []
        if previous_name and previous_name != taxpayer_name:
            changed.append("Name updated")
        if previous_type and previous_type != taxpayer_type:
            changed.append("Type updated")

        if changed:
            base.update(
                {
                    "action": "Taxpayer details updated",
                    "message": ", ".join(changed),
                }
            )
            return base

        return None
