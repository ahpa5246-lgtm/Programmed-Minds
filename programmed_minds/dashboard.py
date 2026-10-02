"""Read-only, loopback-only artifact viewer; no application or network dependencies."""

from __future__ import annotations

import html
import hashlib
import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


MAX_JSON_BYTES = 1024 * 1024
ROLES = (
    ("researcher", "الباحث", "بحث الاحتياج والمصادر"),
    ("research_critic", "ناقد البحث", "فحص الأدلة والاعتراضات"),
    ("improver", "المحسّن", "تطوير الفكرة"),
    ("improvement_critic", "ناقد التحسين", "اختبار جدوى التحسين"),
    ("planner", "المخطّط", "خطة التنفيذ والتسليم"),
    ("plan_critic", "ناقد الخطة", "مراجعة المخاطر والمتطلبات"),
    ("designer", "المصمّم", "تصميم التجربة والواجهة"),
    ("tester", "المختبِر", "تدقيق نتائج الأدوات"),
)

STATUS_LABELS = {
    "passed": "اجتاز", "failed": "فشل", "error": "خطأ", "missing": "غير متاح",
    "not_applicable": "غير منطبق", "blocked": "متوقف", "completed": "مكتمل",
    "complete": "مكتمل", "running": "جارٍ", "stopped": "متوقف",
    "handoff_ready": "التسليم جاهز", "pending": "بانتظار التنفيذ",
    "planned": "التخطيط مكتمل", "verified": "التدقيق موثّق",
}


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _json_text(value: object) -> str:
    return _escape(json.dumps(value, ensure_ascii=False, indent=2))


def _read_json(root: Path, relative: object) -> tuple[dict | None, str]:
    if not isinstance(relative, str) or not relative:
        return None, "مسار الملف غير متاح"
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.suffix != ".json":
        return None, "مسار الملف غير آمن"
    try:
        path = (root / candidate).resolve(strict=True)
        path.relative_to(root)
        if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            return None, "الملف غير صالح أو يتجاوز حد الحجم"
        with path.open("rb") as handle:
            data = handle.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            return None, "الملف يتجاوز حد الحجم"
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            return None, "يجب أن يحتوي الملف على كائن JSON"
        return parsed, ""
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None, "الملف غير متاح أو JSON غير صالح"


def _safe_url(value: object) -> bool:
    if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def _evidence(urls: object) -> str:
    if not isinstance(urls, list):
        urls = []
    links = [f'<li><a href="{_escape(url)}" target="_blank" rel="noopener noreferrer">{_escape(url)}</a></li>' for url in urls if _safe_url(url)]
    if not links:
        return '<p class="muted">لا توجد روابط أدلة صالحة مسجّلة.</p>'
    return '<ul class="evidence" dir="ltr">' + "".join(links) + '</ul><p class="muted">وجود رابط يسجل مصدره؛ لا يثبت صحة محتواه.</p>'


def _badge(status: object) -> str:
    label = STATUS_LABELS.get(str(status), str(status) or "غير متاح")
    state = str(status) if str(status) in STATUS_LABELS else "pending"
    return f'<span class="badge {state}">{_escape(label)}</span>'


def _check_table(report: dict | None, error: str) -> tuple[str, bool]:
    if report is None:
        return f'<p class="empty">غير متاح: {_escape(error)}</p>', False
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        return '<p class="empty">لا توجد نتائج أدوات مسجّلة؛ التحقق غير مكتمل.</p>', False
    rows = []
    valid = report.get("status") == "passed"
    for check in checks:
        if not isinstance(check, dict):
            valid = False
            rows.append('<tr><td colspan="4">نتيجة أداة غير صالحة</td></tr>')
            continue
        status = check.get("status", "missing")
        code = check.get("returncode", check.get("exit_code"))
        display_status = status
        inconsistency = ""
        # Command failures always prevail over a declared pass. Required omissions fail closed.
        if status == "passed" and (type(code) is not int or code != 0):
            valid = False
            display_status = "error"
            inconsistency = "تعارض: التقرير يسجل اجتيازًا دون رمز خروج ناجح."
        if status in {"failed", "error"} or (check.get("required", True) and status != "passed"):
            valid = False
        if status not in {"passed", "failed", "error", "missing", "not_applicable"}:
            valid = False
        command = check.get("argv", [])
        details = {key: check[key] for key in ("reason", "duration", "elapsed", "log", "report_hash") if key in check}
        if inconsistency:
            details["تنبيه"] = inconsistency
        rows.append(f'<tr><th scope="row">{_escape(check.get("name", "أداة غير مسماة"))}</th><td>{_badge(display_status)}</td><td class="number">{_escape(code if code is not None else "—")}</td><td><details><summary>السجل والأمر</summary><pre dir="ltr">{_json_text(command)}</pre><pre>{_json_text(details)}</pre></details></td></tr>')
    return '<div class="table-scroll"><table><thead><tr><th>الأداة</th><th>النتيجة المسجّلة</th><th>رمز الخروج</th><th>التفاصيل</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>', valid


CSS = """
:root{--paper:#f5f3ed;--ink:#243b3b;--muted:#667575;--line:#ced5cd;--accent:#236854;--alert:#9b452d;font-family:Tahoma,Arial,sans-serif;color:var(--ink);background:var(--paper)}
*{box-sizing:border-box}body{margin:0;font-size:18px;line-height:1.8}a{color:var(--accent);text-underline-offset:.25em}a:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:4px}header,main,footer{max-width:1260px;margin:auto;padding:30px 5vw}header{border-bottom:1px solid var(--line)}.brand{font-size:14px;letter-spacing:.08em;color:var(--muted)}h1{font-size:clamp(30px,4vw,46px);margin:8px 0 10px;line-height:1.4}h2{font-size:25px;margin:0 0 18px}h3{font-size:20px;margin:0}p{margin:10px 0}.muted,footer{color:var(--muted);font-size:15px}.run-line{display:flex;align-items:center;flex-wrap:wrap;gap:12px}.notice{border-inline-start:4px solid var(--alert);padding:8px 18px;margin-top:22px}.layout{display:grid;grid-template-columns:270px minmax(0,1fr);gap:46px}.workflow{list-style:none;padding:0;margin:0}.workflow li{border-top:1px solid var(--line);padding:14px 0}.workflow a{text-decoration:none;display:block}.workflow small{display:block;color:var(--muted);font-size:14px}.step-number{font-size:13px;font-variant-numeric:tabular-nums;color:var(--muted);margin-inline-end:12px}.badge{font-size:13px;padding:2px 9px;border:1px solid var(--line);border-radius:4px;display:inline-block}.failed,.error,.missing,.blocked{color:var(--alert)}.passed,.complete,.completed,.handoff_ready{color:var(--accent)}.section{margin-bottom:38px}.stage-detail{border-top:1px solid var(--line);padding:18px 0;scroll-margin-top:18px}.stage-detail>summary{cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:14px}.stage-detail[open]>summary{margin-bottom:18px}.stage-body{padding-inline:16px}.metadata{display:grid;grid-template-columns:1fr 1fr;gap:20px}pre{font-family:inherit;font-size:15px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0 22px;padding:12px 16px;border-inline-start:2px solid var(--line);background:rgba(255,255,255,.45)}.evidence{padding-inline-start:22px;font-size:15px;overflow-wrap:anywhere}.empty{color:var(--alert)}table{border-collapse:collapse;width:100%;font-size:15px;text-align:start}th,td{padding:12px;border-bottom:1px solid var(--line);vertical-align:top}th{font-weight:normal}.number{font-variant-numeric:tabular-nums}.table-scroll{overflow:auto}footer{border-top:1px solid var(--line)}@media(max-width:820px){.layout{grid-template-columns:1fr;gap:32px}.workflow{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}.metadata{grid-template-columns:1fr}header,main,footer{padding:22px 6vw}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
"""


def render_dashboard(run_dir: Path, audit_dir: Path | None = None, checks_dir: Path | None = None) -> str:
    """Return an escaped RTL view; missing/malformed evidence blocks verification."""
    root = Path(run_dir).resolve()
    manifest, manifest_error = _read_json(root, "manifest.json")
    manifest = manifest or {}
    audit_root = Path(audit_dir).resolve() if audit_dir is not None else None
    audit_manifest, audit_error = _read_json(audit_root, "manifest.json") if audit_root is not None else (None, "")
    # These roots are explicit caller inputs. Never follow manifest.planned_run or any report path.
    is_audit = "planned_run" in manifest or manifest.get("status") == "verified"
    plan_manifest = {} if is_audit else manifest
    if is_audit and audit_manifest is None and audit_dir is None:
        audit_manifest, audit_root = manifest, root
    audit_manifest = audit_manifest or {}
    mode = manifest.get("mode", "unknown")
    demo = mode in {"demo", "offline", "replay"} or audit_manifest.get("mode") in {"demo", "offline", "replay"}
    descriptors = manifest.get("stages", [])
    if not isinstance(descriptors, list):
        descriptors = []
    descriptors = [(stage, root) for stage in descriptors]
    if audit_root is not None and audit_root != root:
        audit_stages = audit_manifest.get("stages", [])
        if isinstance(audit_stages, list):
            descriptors.extend((stage, audit_root) for stage in audit_stages)
    workflow = []
    artifacts = []
    complete = bool(manifest) and not manifest_error and not audit_error
    for index, (role, name, purpose) in enumerate(ROLES, 1):
        matching = [(stage, origin) for stage, origin in descriptors if isinstance(stage, dict) and stage.get("role") == role]
        descriptor, origin = matching[-1] if matching else ({}, root)
        artifact, error = _read_json(origin, descriptor.get("artifact"))
        if artifact is not None and (artifact.get("role") != role or not isinstance(artifact.get("data"), dict)):
            artifact, error = None, "هوية المرحلة أو بياناتها غير صالحة"
        if artifact is None:
            complete = False
        badge = _badge("completed" if artifact else "missing")
        workflow.append(f'<li data-role="{role}"><a href="#stage-{role}"><span class="step-number">{index:02}</span>{name}<small>{purpose}</small></a>{badge}</li>')
        if artifact is None:
            body = f'<p class="empty">غير متاح: {_escape(error)}</p>'
        else:
            body = '<h3>المخرجات المسجّلة</h3><pre>' + _json_text(artifact["data"]) + '</pre>'
            body += '<div class="metadata"><div><h3>هوية النموذج</h3><pre>' + _json_text(artifact.get("identity", {})) + '</pre></div><div><h3>الاستخدام المسجّل</h3><pre>' + _json_text(artifact.get("usage", {})) + '</pre></div></div>'
            body += '<h3>الأدلة</h3>' + _evidence(artifact.get("evidence_urls", []))
            hashes = {key: artifact[key] for key in ("input_hash", "output_hash") if key in artifact}
            if hashes:
                body += '<details><summary>بصمات الملفات</summary><pre dir="ltr">' + _json_text(hashes) + '</pre></details>'
        artifacts.append(f'<details class="stage-detail" id="stage-{role}"{ " open" if index == 1 else ""}><summary><span>{index:02} · {name}</span>{badge}</summary><div class="stage-body">{body}</div></details>')
    report_root = Path(checks_dir).resolve() if checks_dir is not None else root
    report, report_error = _read_json(report_root, "checks.json")
    if report is None:
        report, report_error = _read_json(report_root, "checks/report.json")
    checks_html, checks_ok = _check_table(report, report_error)
    # A dashboard renders recorded evidence; it never upgrades incomplete work to release approval.
    linked_report = bool(report) and audit_manifest.get("report_hash") == hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    linked_plan = audit_manifest.get("planned_run") == str(root) and not is_audit
    verified = complete and checks_ok and not demo and mode == "live" and audit_manifest.get("mode") == "live" and plan_manifest.get("status") == "planned" and audit_manifest.get("status") == "verified" and not audit_manifest.get("reasons") and linked_report and linked_plan
    state = "verified" if verified else "blocked"
    state_label = "التدقيق موثّق بالأدلة المسجّلة" if verified else "التحقق غير مكتمل"
    mode_label = "تشغيل تجريبي" if demo else ("تشغيل حي" if mode == "live" else "نوع التشغيل غير متاح")
    notice = "تشغيل تجريبي ببيانات إعادة تشغيل؛ لا يمنح اعتماد إصدار ولا يثبت تشغيل الأدوات فعليًا." if demo else "هذه قراءة للسجلات فقط. مراجعة الذكاء الاصطناعي لا تمنح اعتماد إصدار؛ نتائج الأدوات والأدلة هي المرجع."
    brief = manifest.get("brief", "غير متاح")
    brief_text = _json_text(brief) if isinstance(brief, (dict, list)) else _escape(brief)
    manifest_note = f'<p class="empty">غير متاح: {_escape(manifest_error)}</p>' if manifest_error else ""
    if audit_error:
        manifest_note += f'<p class="empty">التدقيق غير متاح: {_escape(audit_error)}</p>'
    reasons = audit_manifest.get("reasons", [])
    if isinstance(reasons, list) and reasons:
        manifest_note += '<ul class="empty">' + ''.join(f'<li>{_escape(reason)}</li>' for reason in reasons) + '</ul>'
    recorded_statuses = f'<span>الخطة: {_badge(plan_manifest.get("status", "missing"))}</span><span>التدقيق: {_badge(audit_manifest.get("status", "missing"))}</span><span>الأدوات: {_badge(report.get("status", "missing") if report else "missing")}</span>'
    return f'''<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>العقول المبرمجة · سجل العمل</title><style>{CSS}</style></head>
<body><header><div class="brand">PROGRAMMED MINDS / العقول المبرمجة</div><h1>من الفكرة إلى دليل التنفيذ</h1><div class="run-line"><strong>{mode_label}</strong><span class="badge" data-state="{state}">{state_label}</span></div><div class="run-line muted">{recorded_statuses}</div><p class="notice">{notice}</p>{manifest_note}</header>
<main class="layout"><nav aria-label="مراحل العمل"><h2>مسار العقول الثمانية</h2><ol class="workflow">{"".join(workflow)}</ol></nav><div><section class="section"><h2>موجز المهمة</h2><pre>{brief_text}</pre></section><section class="section" aria-label="مخرجات المراحل"><h2>سجل المراحل</h2>{"".join(artifacts)}</section><section class="section"><h2>التحقق بالأدوات</h2><p class="muted">رمز الخروج وحالة كل أداة من التقرير المحفوظ. غياب التقرير يبقي التحقق غير مكتمل.</p>{checks_html}</section></div></main><footer>عارض محلي للقراءة فقط · يعرض البيانات المحفوظة ولا ينفّذ النماذج أو الأدوات.</footer></body></html>'''


def serve(run_dir: Path, host: str = "127.0.0.1", port: int = 8765, *, audit_dir: Path | None = None, checks_dir: Path | None = None) -> None:
    """Serve only the dashboard root over a loopback address until interrupted."""
    if host == "localhost":
        host = "127.0.0.1"
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("Dashboard host must be a loopback IP address") from exc
    if not address.is_loopback:
        raise ValueError("Dashboard host must be a loopback IP address")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # A loopback socket alone does not prevent hostile DNS rebinding.
            hosts = self.headers.get_all("Host", [])
            try:
                parsed_host = urlsplit("//" + hosts[0]) if len(hosts) == 1 else None
                hostname = parsed_host.hostname if parsed_host else None
                local_host = hostname == "localhost" or bool(hostname and ipaddress.ip_address(hostname).is_loopback)
                if not local_host or parsed_host.username or parsed_host.password:
                    raise ValueError("Nonlocal Host header")
            except ValueError:
                self.send_error(403)
                return
            if urlsplit(self.path).path != "/":
                self.send_error(404)
                return
            body = render_dashboard(run_dir, audit_dir=audit_dir, checks_dir=checks_dir).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            # Request paths may contain secrets. Do not write them into terminal logs.
            pass

    server_type = ThreadingHTTPServer
    if address.version == 6:
        import socket

        class IPv6Server(ThreadingHTTPServer):
            address_family = socket.AF_INET6

        server_type = IPv6Server
    with server_type((host, port), Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
