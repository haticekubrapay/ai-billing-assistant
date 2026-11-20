import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from check_gemini import answer_text, generate_content


SEARCH_TOOL = "search_billing_documentation"
INSTRUCTIONS = (
    "You are a billing guide assistant. Use the guide search tool for billing policy "
    "and pricing questions. Search with English terms because the guide is in English. "
    "Answer in the user's language and cite the relevant guide section numbers. "
    "Keep straightforward policy answers to one or two sentences. Say when "
    "the guide does not provide enough information. For questions about a specific "
    "account, explain briefly that you cannot access account records."
)


async def ask(question: str) -> str:
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("billing_mcp_server.py"))],
    )
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        guide_tool = next(tool for tool in tools.tools if tool.name == SEARCH_TOOL)
        payload = {
            "systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
            "contents": [{"role": "user", "parts": [{"text": question}]}],
            "tools": [{"functionDeclarations": [{
                "name": guide_tool.name,
                "description": guide_tool.description,
                "parametersJsonSchema": guide_tool.inputSchema,
            }]}],
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
        }
        choice = generate_content(payload)
        calls = [part["functionCall"] for part in choice["parts"] if "functionCall" in part]
        if not calls:
            print("Tool call: none")
            return answer_text(choice)

        responses = []
        for call in calls:
            arguments = call.get("args", {})
            if call["name"] != SEARCH_TOOL or not isinstance(arguments.get("query"), str):
                raise SystemExit("Gemini returned an unexpected billing tool call.")
            print("Tool call:", json.dumps(call, ensure_ascii=False))
            result = await session.call_tool(SEARCH_TOOL, arguments)
            if result.isError or result.structuredContent is None:
                raise SystemExit("The MCP guide search failed.")
            print("Tool result:", json.dumps(result.structuredContent, ensure_ascii=False, indent=2))
            response = {"name": SEARCH_TOOL, "response": result.structuredContent}
            if "id" in call:
                response["id"] = call["id"]
            responses.append({"functionResponse": response})

        # Keep Gemini's original parts, including any thought signatures.
        payload["contents"].extend([choice, {"role": "user", "parts": responses}])
        payload["toolConfig"]["functionCallingConfig"]["mode"] = "NONE"
        return answer_text(generate_content(payload))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask Gemini a billing guide question.")
    parser.add_argument("question")
    args = parser.parse_args()
    print("\nAnswer:", asyncio.run(ask(args.question)))
