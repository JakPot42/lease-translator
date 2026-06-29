"""
Lease Translator — FastAPI web app.

Routes:
  GET  /            Landing page + demo cards
  POST /analyze     Extract terms from pasted lease text
  GET  /confirm/{id}  Show extracted schema for human review
  POST /confirm/{id}  Run Z3 + explain → result
  GET  /result/{id}   Show verification result
  GET  /api/stats     Health check
"""

import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import config
from lease_explainer import ExplainError, explain_lease
from lease_extractor import ExtractionError, extract_lease_terms
from lease_verifier import LeaseVerifier
from models import LeaseAnalysis, get_db, init_db
from seed_data import load_seed_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db_gen = get_db()
    db = next(db_gen)
    load_seed_data(db)
    yield


app = FastAPI(title=config.APP_TITLE, lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


def _demo_badge(result: dict | None) -> str:
    if not result:
        return ""
    return result.get("status", "")


templates.env.globals["demo_badge"] = _demo_badge


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    demos = db.query(LeaseAnalysis).order_by(LeaseAnalysis.id).limit(3).all()
    demo_items = []
    for i, d in enumerate(demos, 1):
        z3 = d.get_z3_result()
        status = z3.get("status", "") if z3 else ""
        conflicts = len(z3.get("conflicts", [])) if z3 else 0
        schema = d.get_confirmed()
        address = schema.get("property", {}).get("address", "Demo Property") if schema else "Demo Property"
        demo_items.append(
            {
                "id": d.id,
                "n": i,
                "address": address,
                "status": status,
                "conflicts": conflicts,
            }
        )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "demo_mode": config.DEMO_MODE,
            "demo_items": demo_items,
            "title": config.APP_TITLE,
        },
    )


@app.post("/analyze")
async def analyze(
    request: Request,
    lease_text: str = Form(...),
    db: Session = Depends(get_db),
):
    _MAX_LEASE_CHARS = 50_000
    lease_text = lease_text.strip()
    if len(lease_text) > _MAX_LEASE_CHARS:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "demo_mode": config.DEMO_MODE,
                "demo_items": [],
                "title": config.APP_TITLE,
                "error": f"Lease text too long ({len(lease_text):,} chars). Maximum is {_MAX_LEASE_CHARS:,} characters.",
            },
        )
    if len(lease_text) < 50:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "demo_mode": config.DEMO_MODE,
                "demo_items": [],
                "title": config.APP_TITLE,
                "error": "Please paste a complete lease agreement (at least 50 characters).",
            },
        )

    try:
        schema = extract_lease_terms(lease_text)
    except ExtractionError as e:
        demos = db.query(LeaseAnalysis).order_by(LeaseAnalysis.id).limit(3).all()
        demo_items = []
        for i, d in enumerate(demos, 1):
            z3 = d.get_z3_result()
            status = z3.get("status", "") if z3 else ""
            demo_items.append({"id": d.id, "n": i, "status": status, "conflicts": 0, "address": ""})
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "demo_mode": config.DEMO_MODE,
                "demo_items": demo_items,
                "title": config.APP_TITLE,
                "error": f"Extraction failed: {e}",
            },
        )

    analysis = LeaseAnalysis(
        raw_text=lease_text,
        extracted_json=json.dumps(schema),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return RedirectResponse(f"/confirm/{analysis.id}", status_code=303)


@app.get("/confirm/{analysis_id}", response_class=HTMLResponse)
async def confirm_get(request: Request, analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.get(LeaseAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    schema = analysis.get_extracted()
    if not schema:
        raise HTTPException(status_code=400, detail="No extracted schema found")

    return templates.TemplateResponse(
        request,
        "confirm.html",
        {
            "analysis": analysis,
            "schema": schema,
            "title": config.APP_TITLE,
        },
    )


@app.post("/confirm/{analysis_id}")
async def confirm_post(
    request: Request,
    analysis_id: int,
    db: Session = Depends(get_db),
):
    analysis = db.get(LeaseAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    schema = analysis.get_extracted()
    if not schema:
        raise HTTPException(status_code=400, detail="No extracted schema found")

    # Save confirmed schema
    analysis.confirmed_json = json.dumps(schema)

    # Run Z3 verification
    z3_result = LeaseVerifier().verify(schema)
    analysis.z3_result_json = json.dumps(z3_result.to_dict())

    # Generate plain-English explanation
    try:
        plain = explain_lease(schema, z3_result.to_dict())
        analysis.plain_english_json = json.dumps(plain)
    except ExplainError:
        analysis.plain_english_json = json.dumps(
            {
                "summary": (
                    "No logical contradictions found."
                    if z3_result.status == "PASS"
                    else f"{len(z3_result.conflicts)} contradiction(s) found."
                ),
                "clause_explanations": [],
                "contradiction_explanations": [
                    {"clauses": c.clauses, "plain_english": c.explanation}
                    for c in z3_result.conflicts
                ],
                "disclaimer": "Plain-language explanation unavailable. Technical details are shown above.",
            }
        )

    db.commit()
    return RedirectResponse(f"/result/{analysis_id}", status_code=303)


@app.get("/result/{analysis_id}", response_class=HTMLResponse)
async def result(request: Request, analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.get(LeaseAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    z3 = analysis.get_z3_result()
    plain = analysis.get_plain_english()
    schema = analysis.get_confirmed() or analysis.get_extracted()

    if not z3:
        raise HTTPException(status_code=400, detail="Analysis not yet complete")

    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "analysis": analysis,
            "z3": z3,
            "plain": plain,
            "schema": schema,
            "title": config.APP_TITLE,
            "demo_mode": config.DEMO_MODE,
        },
    )


@app.get("/api/stats")
async def stats(db: Session = Depends(get_db)):
    total = db.query(LeaseAnalysis).count()
    passed = sum(
        1
        for a in db.query(LeaseAnalysis).all()
        if a.get_z3_result() and a.get_z3_result().get("status") == "PASS"
    )
    return {
        "app": config.APP_TITLE,
        "demo_mode": config.DEMO_MODE,
        "total_analyses": total,
        "passed": passed,
        "failed": total - passed,
    }
