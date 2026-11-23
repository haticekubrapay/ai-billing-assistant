import argparse
import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool

from check_gemini import answer_text, generate_content


SEARCH_TOOL = "search_billing_documentation"
BILL_TOOL = "get_my_bill"
DETAIL_TOOL = "get_my_bill_details"
PAYMENT_TOOL = "prepare_bill_payment"
DEMO_SUBSCRIBER = "1001"
GATEWAY_URL = "http://127.0.0.1:8080"
BILL_DECLARATION = {
    "name": BILL_TOOL,
    "description": "Look up the local demo subscriber's bill total, paid amount, and balance.",
    "parametersJsonSchema": {
        "type": "object",
        "properties": {
            "month": {"type": "integer", "minimum": 1, "maximum": 12},
            "year": {"type": "integer", "minimum": 1, "maximum": 9999},
        },
        "required": ["month", "year"],
    },
}
DETAIL_DECLARATION = {
    **BILL_DECLARATION,
    "name": DETAIL_TOOL,
    "description": "Look up the demo subscriber's billed usage and itemized charges for a month.",
}
PAYMENT_DECLARATION = {
    **BILL_DECLARATION,
    "name": PAYMENT_TOOL,
    "description": "Prepare a simulated payment of the full remaining balance for the demo subscriber.",
}
INSTRUCTIONS = (
    "You are a billing assistant. Use the guide search tool for billing policy "
    "and pricing questions. Search with English terms because the guide is in English. "
    "Answer in the user's language and cite the relevant guide section numbers. "
    "Keep straightforward policy answers to one or two sentences. Say when "
    "the guide does not provide enough information. For the user's own bill total "
    "or balance, call get_my_bill when the month and year are known. For example, "
    "'Ekim 2026 faturam ne kadar?' requests month 10 and year 2026. Ask for a "
    "missing period field. Use the tool result for amounts. If the user asks for "
    "another account, explain that only the demo account is available. To explain "
    "why a particular bill is high, call get_my_bill_details first, then search "
    "the guide for the pricing rules relevant to the returned charges. Search using "
    "specific terms such as 'additional phone minutes cost' and 'additional internet "
    "blocks cost' instead of general terms about a high bill. For itemized bills, "
    "state the total and each charge in US dollars. Cite only retrieved sections "
    "that directly explain the charges. If billed usage is missing or charges are unitemized, "
    "say that the specific cause cannot be determined from that bill. For an "
    "explicit request to pay the full remaining balance, call prepare_bill_payment "
    "with the requested month and year. This demo supports full balance payments only. "
    "The interface handles confirmation."
)


async def get_my_bill(arguments: dict, *, detailed: bool = False, subscriber: str = DEMO_SUBSCRIBER) -> dict:
    month, year = arguments.get("month"), arguments.get("year")
    if (
        arguments.keys() != {"month", "year"}
        or type(month) is not int or not 1 <= month <= 12
        or type(year) is not int or not 1 <= year <= 9999
    ):
        return {"error": "A valid billing month and year are required."}

    path = f"/api/v1/bills/{subscriber}"
    headers = {}
    if detailed:
        token = os.environ.get("USAGE_OPERATOR_TOKEN", "").strip()
        if not token:
            return {"error": "The operator token is required for bill details."}
        path += "/details"
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(
                f"{GATEWAY_URL}{path}",
                headers=headers,
                params={"month": month, "year": year},
            )
    except httpx.RequestError:
        return {"error": "The billing gateway is unavailable."}

    if response.status_code == 404:
        return {"error": "No bill was found for that month and year."}
    if response.status_code != 200:
        return {"error": f"Bill lookup failed (HTTP {response.status_code})."}
    return response.json()


async def pay_with_confirmation(arguments: dict) -> str:
    token = os.environ.get("USAGE_OPERATOR_TOKEN", "").strip()
    if not token:
        return "Set USAGE_OPERATOR_TOKEN before requesting a simulated payment."

    bill = await get_my_bill(arguments, detailed=True)
    if "error" in bill:
        return bill["error"]

    amount = Decimal(str(bill["remaining_balance"]))
    if amount <= 0:
        return "This bill has no remaining balance."

    period = f"{arguments['year']:04d}-{arguments['month']:02d}"
    try:
        confirmation = input(
            f"Simulate a payment of ${amount:.2f} for subscriber {DEMO_SUBSCRIBER}, "
            f"bill {period}? Type PAY to confirm: "
        )
    except (EOFError, KeyboardInterrupt):
        return "Payment cancelled."
    if confirmation.strip() != "PAY":
        return "Payment cancelled."

    return await submit_payment(arguments, amount)


async def submit_payment(arguments: dict, amount: Decimal, *, subscriber: str = DEMO_SUBSCRIBER) -> str:
    token = os.environ.get("USAGE_OPERATOR_TOKEN", "").strip()
    if not token:
        return "Set USAGE_OPERATOR_TOKEN before requesting a simulated payment."
    transaction_id = uuid4().hex
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.post(
                f"{GATEWAY_URL}/api/v1/bills/pay",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    **arguments,
                    "subscriber_no": subscriber,
                    "amount": str(amount),
                    "transaction_id": transaction_id,
                    "confirmed": True,
                },
            )
    except httpx.RequestError:
        return f"Payment outcome unknown. Check the balance before retrying (transaction {transaction_id})."

    if response.status_code >= 500:
        return f"Payment outcome unknown. Check the balance before retrying (transaction {transaction_id})."
    if response.status_code != 200:
        return f"Payment rejected (HTTP {response.status_code})."

    remaining = Decimal(str(response.json()["remaining_balance"]))
    return f"Simulated payment recorded. Remaining balance: ${remaining:.2f}."


@asynccontextmanager
async def open_billing_mcp() -> AsyncIterator[tuple[ClientSession, Tool]]:
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("billing_mcp_server.py"))],
    )
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        guide_tool = next(tool for tool in tools.tools if tool.name == SEARCH_TOOL)
        print("Billing MCP ready")
        yield session, guide_tool


async def ask(
    question: str,
    payment_handler: Callable[[dict], Awaitable[str]] = pay_with_confirmation,
    *, subscriber: str = DEMO_SUBSCRIBER,
    mcp: tuple[ClientSession, Tool] | None = None,
) -> str:
    if mcp is None:
        async with open_billing_mcp() as connection:
            return await ask(question, payment_handler, subscriber=subscriber, mcp=connection)

    session, guide_tool = mcp
    payload = {
        "systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "tools": [{"functionDeclarations": [{
            "name": guide_tool.name,
            "description": guide_tool.description,
            "parametersJsonSchema": guide_tool.inputSchema,
        }, BILL_DECLARATION, DETAIL_DECLARATION, PAYMENT_DECLARATION]}],
        "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
    }
    for round_number in range(4):
        if round_number == 3:
            payload["toolConfig"]["functionCallingConfig"]["mode"] = "NONE"
        choice = await asyncio.to_thread(generate_content, payload)
        calls = [part["functionCall"] for part in choice["parts"] if "functionCall" in part]
        if not calls:
            if round_number == 0:
                print("Tool call: none")
            return answer_text(choice)

        if round_number == 3:
            return "The agent reached its tool-call limit."

        responses = []
        for call in calls:
            arguments = call.get("args", {})
            name = call["name"]
            print("Tool call:", json.dumps(call, ensure_ascii=False))
            if name == BILL_TOOL:
                output = await get_my_bill(arguments, subscriber=subscriber)
            elif name == DETAIL_TOOL:
                output = await get_my_bill(arguments, detailed=True, subscriber=subscriber)
            elif name == PAYMENT_TOOL:
                return await payment_handler(arguments)
            elif name == SEARCH_TOOL and isinstance(arguments.get("query"), str):
                result = await session.call_tool(SEARCH_TOOL, arguments)
                output = result.structuredContent
                if result.isError or output is None:
                    output = {"error": "The MCP guide search failed."}
            else:
                output = {"error": "Unknown tool or invalid arguments."}
            print("Tool result:", json.dumps(output, ensure_ascii=False, indent=2))
            response = {"name": name, "response": output}
            if "id" in call:
                response["id"] = call["id"]
            responses.append({"functionResponse": response})

        # Keep Gemini's original parts, including any thought signatures.
        payload["contents"].extend([choice, {"role": "user", "parts": responses}])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask Gemini about billing rules or the demo bill.")
    parser.add_argument("question")
    args = parser.parse_args()
    print("\nAnswer:", asyncio.run(ask(args.question)))
