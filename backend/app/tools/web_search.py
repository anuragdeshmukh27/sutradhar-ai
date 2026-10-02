from . import Tool, register

CANNED = [
    {"title": "Tips for organising a college tech fest", "href": "https://example.com/techfest-guide",
     "body": "Book the venue early, secure sponsors, and plan a clear day-wise schedule."},
    {"title": "Typical tech fest budget breakdown", "href": "https://example.com/budget",
     "body": "Venue, food, prizes, publicity and logistics make up most of the budget."},
]


@register
class WebSearch(Tool):
    name = "web_search"
    description = "Search the web (DuckDuckGo; canned results if offline). Read-only."
    args_schema = {"query": "search query"}
    reversible = True  # no side effects

    def run(self, args, ctx):
        query = str(args.get("query", "tech fest"))
        results, source = CANNED, "offline-fallback"
        try:
            from duckduckgo_search import DDGS

            found = list(DDGS(timeout=5).text(query, max_results=3))
            if found:
                results, source = found, "duckduckgo"
        except Exception:  # offline or rate-limited: use canned results
            pass
        return {"ok": True, "summary": f"Search completed for '{query}' with {len(results)} results",
                "data": {"results": results, "source": source}, "undo_payload": {}}

    def undo(self, record):
        return {"ok": True, "summary": "Nothing to undo (read-only)"}
