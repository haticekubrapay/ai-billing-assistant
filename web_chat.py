import os
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from secrets import compare_digest
from time import monotonic
from uuid import uuid4

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from billing_agent import DEMO_SUBSCRIBER, ask, get_my_bill, open_billing_mcp, submit_payment


SESSION_COOKIE = "billing_session"
SESSION_SECONDS = 3600
sessions: dict[str, tuple[float, str]] = {}
pending: dict[str, tuple[float, str, dict, Decimal]] = {}


@asynccontextmanager
async def lifespan(app: Starlette):
    async with open_billing_mcp() as mcp:
        yield {"billing_mcp": mcp}


def current_session(request: Request) -> tuple[str, str] | None:
    key = request.cookies.get(SESSION_COOKIE, "")
    session = sessions.get(key)
    if session is None or session[0] <= monotonic():
        sessions.pop(key, None)
        return None
    return key, session[1]


async def session_status(request: Request) -> JSONResponse:
    session = current_session(request)
    return JSONResponse(
        {"subscriber": session[1]} if session else {}, status_code=200 if session else 401
    )


async def login(request: Request) -> JSONResponse:
    try:
        data = await read_json(request)
    except ValueError:
        return JSONResponse({"error": "Geçersiz giriş isteği."}, status_code=400)
    expected = os.environ.get("BILLING_DEMO_PASSWORD", "")
    if not expected:
        return JSONResponse({"error": "Sunucuda BILLING_DEMO_PASSWORD ayarlanmalı."}, status_code=503)
    password = data.get("password")
    if not isinstance(password, str) or len(password) > 256 or not compare_digest(password.encode(), expected.encode()):
        return JSONResponse({"error": "Demo şifresi yanlış."}, status_code=401)
    now = monotonic()
    for key, (expires, _) in list(sessions.items()):
        if expires <= now:
            sessions.pop(key)
    sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
    key = uuid4().hex
    sessions[key] = (now + SESSION_SECONDS, DEMO_SUBSCRIBER)
    response = JSONResponse({"subscriber": DEMO_SUBSCRIBER})
    response.set_cookie(SESSION_COOKIE, key, max_age=SESSION_SECONDS, httponly=True, samesite="strict")
    return response


async def logout(request: Request) -> JSONResponse:
    try:
        await read_json(request)
    except ValueError:
        return JSONResponse({"error": "Geçersiz çıkış isteği."}, status_code=400)
    key = request.cookies.get(SESSION_COOKIE, "")
    sessions.pop(key, None)
    for payment_id, proposal in list(pending.items()):
        if proposal[1] == key:
            pending.pop(payment_id)
    response = JSONResponse({})
    response.delete_cookie(SESSION_COOKIE)
    return response


async def home(request: Request) -> FileResponse:
    return FileResponse(Path(__file__).with_name("web") / "index.html")


async def read_json(request: Request) -> dict:
    if request.headers.get("origin") != str(request.base_url).rstrip("/"):
        raise ValueError("Request must come from the demo page.")
    data = await request.json()
    if not isinstance(data, dict):
        raise ValueError("Invalid request.")
    return data


async def chat(request: Request) -> JSONResponse:
    session = current_session(request)
    if session is None:
        return JSONResponse({"error": "Önce demo hesabına giriş yap."}, status_code=401)
    session_id, subscriber = session
    try:
        data = await read_json(request)
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    question = data.get("question")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        return JSONResponse({"error": "Enter a question of up to 2,000 characters."}, status_code=400)

    proposal = None

    async def prepare(arguments: dict) -> str:
        nonlocal proposal
        bill = await get_my_bill(arguments, detailed=True, subscriber=subscriber)
        if "error" in bill:
            return bill["error"]
        amount = Decimal(str(bill["remaining_balance"]))
        if amount <= 0:
            return "Bu faturanın kalan borcu yok."
        proposal = (arguments, amount)
        period = f"{arguments['month']:02d}/{arguments['year']}"
        return f"{subscriber} numaralı abonenin {period} faturası için {amount:.2f} USD simülasyon ödemesini onaylıyor musun?"

    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return JSONResponse({"error": "Sunucuda GEMINI_API_KEY tanımlı olmalı."}, status_code=503)
    try:
        answer = await ask(
            question.strip(), prepare, subscriber=subscriber, mcp=request.state.billing_mcp
        )
    except SystemExit as error:
        return JSONResponse({"error": str(error)}, status_code=502)
    payment_id = None
    if proposal is not None:
        if current_session(request) != session:
            return JSONResponse({"error": "Oturum sona erdi."}, status_code=401)
        now = monotonic()
        for key in list(pending):
            if pending[key][0] <= now:
                pending.pop(key)
        if len(pending) >= 100:
            return JSONResponse({"error": "Çok fazla bekleyen ödeme var. Birkaç dakika sonra tekrar dene."}, status_code=503)
        payment_id = uuid4().hex
        pending[payment_id] = (now + 300, session_id, *proposal)
    return JSONResponse({"answer": answer, "payment": payment_id})


async def payment(request: Request) -> JSONResponse:
    session = current_session(request)
    if session is None:
        return JSONResponse({"error": "Önce demo hesabına giriş yap."}, status_code=401)
    session_id, subscriber = session
    try:
        data = await read_json(request)
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    key, confirmed = data.get("id"), data.get("confirmed")
    if not isinstance(key, str) or type(confirmed) is not bool:
        return JSONResponse({"error": "Geçersiz ödeme onayı."}, status_code=400)
    proposal = pending.get(key)
    if proposal is None or proposal[1] != session_id or proposal[0] <= monotonic():
        return JSONResponse({"error": "Ödeme onayının süresi doldu. Yeniden sor."}, status_code=409)
    pending.pop(key)
    if not confirmed:
        return JSONResponse({"answer": "Ödeme iptal edildi."})
    _, _, arguments, amount = proposal
    return JSONResponse({"answer": await submit_payment(arguments, amount, subscriber=subscriber)})


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/", home),
        Route("/session", session_status),
        Route("/login", login, methods=["POST"]),
        Route("/logout", logout, methods=["POST"]),
        Route("/chat", chat, methods=["POST"]),
        Route("/payment", payment, methods=["POST"]),
    ],
    middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])],
)
