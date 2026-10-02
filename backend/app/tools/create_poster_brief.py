from ..config import FILES_DIR
from . import Tool, register


@register
class CreatePosterBrief(Tool):
    name = "create_poster_brief"
    description = "Write a publicity / poster brief (text file)."
    args_schema = {"event_name": "event name", "tagline": "tagline", "details": "dates, venue, audience"}
    reversible = True

    def run(self, args, ctx):
        FILES_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"poster_brief_{ctx.get('run_id', 'run')}_{ctx.get('node_id', 'node')}.txt"
        text = (f"POSTER BRIEF\nEvent: {args.get('event_name', 'Tech Fest')}\n"
                f"Tagline: {args.get('tagline', '')}\nDetails: {args.get('details', '')}\n")
        (FILES_DIR / fname).write_text(text, encoding="utf-8")
        return {"ok": True, "summary": f"Poster brief written for {args.get('event_name', 'Tech Fest')}",
                "data": {"file": fname}, "undo_payload": {"file": fname}}

    def undo(self, record):
        (FILES_DIR / record["undo_payload"]["file"]).unlink(missing_ok=True)
        return {"ok": True, "summary": "Poster brief deleted"}
