from fastapi import FastAPI

from bill_router import router as bill_router
from usage_router import router as usage_router


app = FastAPI(title="AI Billing Support Assistant")
app.include_router(usage_router)
app.include_router(bill_router)
