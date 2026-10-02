import os

from . import Tool, register


@register
class BookVenue(Tool):
    name = "book_venue"
    description = "Book a venue with a (mock) vendor. Irreversible and may be declined."
    args_schema = {"venue": "venue name", "date": "date or range", "capacity": "guests"}
    reversible = False

    def run(self, args, ctx):
        venue = str(args.get("venue", "Main auditorium"))
        if os.getenv("FAILURE_INJECTION", "false").lower() == "true":
            return {"ok": False, "summary": "Venue declined", "data": {}, "undo_payload": {}}
        return {"ok": True, "summary": f"Venue booked: {venue}", "data": {"venue": venue},
                "undo_payload": {}}

    def undo(self, record):
        return {"ok": False, "summary": "Venue bookings cannot be undone automatically"}
