"""Vercel's Python function: the whole NIMUS OS API in one FastAPI app (routes in cloud/)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402

from cloud.commercial import router as commercial  # noqa: E402
from cloud.finance import router as finance  # noqa: E402
from cloud.profitability import router as profitability  # noqa: E402
from cloud.production import router as production  # noqa: E402
from cloud.products import router as products  # noqa: E402
from cloud.routes import router  # noqa: E402

app = FastAPI(title='NIMUS OS', docs_url='/api/docs', openapi_url='/api/openapi.json', redoc_url=None)
app.include_router(router)
app.include_router(production)
app.include_router(products)
app.include_router(commercial)
app.include_router(finance)
app.include_router(profitability)
