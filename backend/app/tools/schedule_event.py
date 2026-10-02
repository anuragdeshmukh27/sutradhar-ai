from ..db import CalendarEvent, session
from . import Tool, register


@register
class ScheduleEvent(Tool):
    name = "schedule_event"
    description = "Add an event to the sandbox calendar. Undo deletes it."
    args_schema = {"title": "event title", "date": "date or date range", "details": "notes"}
    reversible = True

    def run(self, args, ctx):
        with session() as s:
            ev = CalendarEvent(run_id=ctx.get("run_id"), title=str(args.get("title", "Event")),
                               date=str(args.get("date", "TBD")), details=str(args.get("details", "")))
            s.add(ev)
            s.flush()
            eid = ev.id
        return {"ok": True, "summary": f"Scheduled '{args.get('title', 'Event')}' on {args.get('date', 'TBD')}",
                "data": {"event_id": eid}, "undo_payload": {"event_id": eid}}

    def undo(self, record):
        with session() as s:
            ev = s.get(CalendarEvent, record["undo_payload"]["event_id"])
            if not ev:
                return {"ok": False, "summary": "Event not found"}
            ev.status = "deleted"
        return {"ok": True, "summary": "Calendar event deleted"}
