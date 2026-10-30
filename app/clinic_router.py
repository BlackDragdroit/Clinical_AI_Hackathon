"""Clinic-internal routes. Owner: SWE 1.

Routes here are only included when PORTAL_ONLY is not set. In a split deployment the portal pod
never serves these endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import audit, i18n

router = APIRouter()


def _page_audit(request: Request, name: str, **ctx) -> HTMLResponse:
    """Minimal _page variant for audit pages (no cookie banner, no lang toggle cookie needed)."""
    from app.portal_router import _page
    return _page(request, name, **ctx)


@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, request_id: str | None = None):
    # clinic-internal: in production this sits behind the clinic login (footer says so)
    lang = i18n.resolve_lang(request)
    resp = _page_audit(request, "audit.html", v=audit.view(request_id, lang), lang=lang, other_lang=i18n.other_lang)
    if request.query_params.get("lang"):
        i18n.remember(resp, lang)
    return resp


@router.get("/audit/apple", response_class=HTMLResponse)
def audit_page_apple(request: Request, request_id: str | None = None):
    # same data and query params as /audit, second look (formal audit record) for side-by-side review
    lang = i18n.resolve_lang(request)
    resp = _page_audit(request, "audit_apple.html", v=audit.view(request_id, lang, base="/audit/apple"), lang=lang, other_lang=i18n.other_lang)
    if request.query_params.get("lang"):
        i18n.remember(resp, lang)
    return resp


@router.get("/audit.json")
def audit_json(request_id: str | None = None):
    v = audit.view(request_id)
    return JSONResponse({"chain_ok": v["chain_ok"], "coverage": v["coverage"], "entries": audit.entries(request_id),
                         "first_broken": v["first_broken"], "entry_count": v["entry_count"], "last_hash": v["head"],
                         "request_id": v["request_id"],
                         "requests": [{k: r[k] for k in ("id", "status", "patient_ref", "expected_name", "contact",
                                                         "covered", "misdelivery")} for r in v["requests"]],
                         "misdelivery": {code: [{"request_id": m["request_id"], "seq": m["seq"]} for m in found]
                                         for code, found in v["misdelivery"].items()}})
