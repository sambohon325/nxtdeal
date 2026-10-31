"""Actual dealer application with preview-only CORS, no production configuration."""
import os
from fastapi.middleware.cors import CORSMiddleware
if os.environ.get("NXTDEAL_SYNTHETIC") != "true":
    raise RuntimeError("Synthetic preview environment required")
from api.app import app
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3317"],
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

@app.get('/synthetic/identity')
def synthetic_identity():
    return {'scope':'synthetic_only','service':'dealer','delivery_enabled':False}
