from ..db import Email, session
from . import Tool, register


@register
class SendEmail(Tool):
    name = "send_email"
    description = "Send an email (sandbox outbox). Undo recalls it."
    args_schema = {"to": "recipient", "subject": "subject line", "body": "email body"}
    reversible = True

    def run(self, args, ctx):
        with session() as s:
            e = Email(run_id=ctx.get("run_id"), to=str(args.get("to", "team@example.com")),
                      subject=str(args.get("subject", "(no subject)")), body=str(args.get("body", "")))
            s.add(e)
            s.flush()
            eid = e.id
        return {"ok": True, "summary": f"Email sent to {args.get('to', 'team@example.com')}: {args.get('subject', '')}",
                "data": {"email_id": eid}, "undo_payload": {"email_id": eid}}

    def undo(self, record):
        with session() as s:
            e = s.get(Email, record["undo_payload"]["email_id"])
            if not e:
                return {"ok": False, "summary": "Email not found"}
            e.status = "recalled"
        return {"ok": True, "summary": "Email recalled"}
