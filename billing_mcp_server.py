from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from billing_documentation import (
    GUIDE_PATH,
    BillingSearchIndex,
    BillingSection,
    load_billing_sections,
)


class BillingSearchResult(TypedDict):
    document: str
    matches: list[BillingSection]


mcp = FastMCP("Billing Documentation")
index = BillingSearchIndex(load_billing_sections())


@mcp.tool()
def search_billing_documentation(query: str) -> BillingSearchResult:
    """Find relevant sections of the billing guide for a pricing or policy question."""
    return {"document": GUIDE_PATH.name, "matches": index.search(query)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
