from ..config import FILES_DIR
from . import Tool, register


@register
class RequestPermission(Tool):
    name = "request_permission"
    description = "Draft a permission letter to an authority (saved as a text file)."
    args_schema = {"authority": "who to address", "purpose": "what permission is for", "details": "dates, numbers"}
    reversible = True

    def run(self, args, ctx):
        FILES_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"permission_{ctx.get('run_id', 'run')}_{ctx.get('node_id', 'node')}.txt"
        letter = (f"To,\n{args.get('authority', 'The Principal')}\n\nSubject: Request for permission\n\n"
                  f"Respected Sir/Madam,\n\nWe request permission for: {args.get('purpose', 'our event')}.\n"
                  f"{args.get('details', '')}\n\nThank you.\nOrganising Committee\n")
        (FILES_DIR / fname).write_text(letter, encoding="utf-8")
        return {"ok": True, "summary": f"Permission letter drafted for {args.get('authority', 'The Principal')}",
                "data": {"file": fname}, "undo_payload": {"file": fname}}

    def undo(self, record):
        p = FILES_DIR / record["undo_payload"]["file"]
        p.unlink(missing_ok=True)
        return {"ok": True, "summary": "Permission letter deleted"}
