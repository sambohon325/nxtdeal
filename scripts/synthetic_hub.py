"""Synthetic personal-account preview, never a production Hub replacement."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from hub_core.mysales_personal import router
from hub_core.mysales_assistants import router as assistants

if os.environ.get("NXTDEAL_SYNTHETIC") != "true":
    raise RuntimeError("Synthetic preview environment required")
app = FastAPI(title="Synthetic MySales rehearsal")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3317"],
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)
app.include_router(router)
app.include_router(assistants)

@app.get('/synthetic/identity')
def synthetic_identity():
    return {'scope':'synthetic_only','service':'hub','delivery_enabled':False}
