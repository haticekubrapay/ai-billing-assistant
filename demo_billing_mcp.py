import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


DEMO_QUERIES = (
    "How much does extra internet cost?",
    "Can I make a partial payment?",
    "What is the billing dispute window?",
)


async def search(session: ClientSession, query: str) -> dict:
    result = await session.call_tool("search_billing_documentation", {"query": query})
    if result.isError or result.structuredContent is None:
        raise SystemExit(f"MCP call failed for {query!r}: {result.content}")
    return result.structuredContent


async def run_demo(queries: list[str], interactive: bool) -> None:
    server_path = Path(__file__).with_name("billing_mcp_server.py")
    server = StdioServerParameters(command=sys.executable, args=[str(server_path)])
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        if interactive:
            print("Ask a question in English about the billing guide. Type 'exit' to quit.")
            while True:
                try:
                    query = input("\nYou: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    return
                if query.casefold() in {"çık", "exit", "quit"}:
                    return
                if not query:
                    continue
                content = await search(session, query)
                matches = content["matches"]
                if matches:
                    match = matches[0]
                    print(f"\nGuide · {match['section']} {match['heading']}")
                    print(match["text"])
                else:
                    print("No matching section found in the billing guide.")

        for query in queries:
            trace = {
                "tool": "search_billing_documentation",
                "arguments": {"query": query},
                "result": await search(session, query),
            }
            print(json.dumps(trace, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Try the billing guide MCP search.")
    parser.add_argument("query", nargs="*", help="Optional questions. Quote each question.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Ask questions in the terminal.")
    args = parser.parse_args()
    if args.interactive and args.query:
        parser.error("Pass questions or use --interactive.")
    asyncio.run(run_demo(args.query or list(DEMO_QUERIES), args.interactive))
