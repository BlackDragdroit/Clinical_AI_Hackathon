"""Clinic-internal routes. Owner: SWE 1.

Routes here are only included when PORTAL_ONLY is not set. In a split deployment the portal pod
never serves these endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import audit, db, i18n
from app.config import settings

router = APIRouter()


def _page_audit(request: Request, name: str, **ctx) -> HTMLResponse:
    """Minimal _page variant for audit pages (no cookie banner, no lang toggle cookie needed)."""
    from app.portal_router import _page
    return _page(request, name, **ctx)


def _audit_auth(request: Request) -> bool:
    """Return True if access is allowed (token empty or token matches)."""
    if not settings.audit_token:
        return True
    provided = request.query_params.get("token", "")
    if not provided:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            provided = auth[7:]
    return provided == settings.audit_token


@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, request_id: str | None = None):
    # clinic-internal: in production this sits behind the clinic login (footer says so)
    if not _audit_auth(request):
        return HTMLResponse("Zugriff verweigert", status_code=403)
    lang = i18n.resolve_lang(request)
    resp = _page_audit(request, "audit.html", v=audit.view(request_id, lang), lang=lang, other_lang=i18n.other_lang)
    if request.query_params.get("lang"):
        i18n.remember(resp, lang)
    return resp


@router.get("/audit/apple", response_class=HTMLResponse)
def audit_page_apple(request: Request, request_id: str | None = None):
    # same data and query params as /audit, second look (formal audit record) for side-by-side review
    if not _audit_auth(request):
        return HTMLResponse("Zugriff verweigert", status_code=403)
    lang = i18n.resolve_lang(request)
    resp = _page_audit(request, "audit_apple.html", v=audit.view(request_id, lang, base="/audit/apple"), lang=lang, other_lang=i18n.other_lang)
    if request.query_params.get("lang"):
        i18n.remember(resp, lang)
    return resp


@router.post("/admin/purge")
def admin_purge():
    result = db.purge(settings.quarantine_ttl_days, settings.token_ttl_days)
    return {**result, "ttl_days": {"quarantine": settings.quarantine_ttl_days, "token": settings.token_ttl_days}}


@router.get("/audit.json")
def audit_json(request: Request, request_id: str | None = None):
    if not _audit_auth(request):
        return JSONResponse({"error": "Zugriff verweigert"}, status_code=403)
    v = audit.view(request_id)
    return JSONResponse({"chain_ok": v["chain_ok"], "coverage": v["coverage"], "entries": audit.entries(request_id),
                         "first_broken": v["first_broken"], "entry_count": v["entry_count"], "last_hash": v["head"],
                         "request_id": v["request_id"],
                         "requests": [{k: r[k] for k in ("id", "status", "patient_ref", "expected_name", "contact",
                                                         "covered", "misdelivery")} for r in v["requests"]],
                         "misdelivery": {code: [{"request_id": m["request_id"], "seq": m["seq"]} for m in found]
                                         for code, found in v["misdelivery"].items()}})
