import json
import hashlib
import http.client
import queue
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from programmed_minds.dashboard import render_dashboard, serve


ROLES = ["researcher", "research_critic", "improver", "improvement_critic", "planner", "plan_critic", "designer", "tester"]


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run"
        self.run.mkdir()

    def write(self, name, value):
        path = self.run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def complete(self, mode="demo"):
        stages = []
        for role in ROLES:
            self.write(f"{role}.json", {"role": role, "data": {"summary": "مراجعة"}, "identity": {"model": "fixture"}, "usage": {"output_tokens": 10}})
            stages.append({"role": role, "artifact": f"{role}.json"})
        self.write("manifest.json", {"status": "completed", "mode": mode, "brief": {"title": "مشروع"}, "stages": stages})

    def test_absent_and_malformed_manifest_fail_closed(self):
        page = render_dashboard(self.run)
        self.assertIn("غير متاح", page)
        self.assertIn("data-state=\"blocked\"", page)
        (self.run / "manifest.json").write_text("{broken", encoding="utf-8")
        page = render_dashboard(self.run)
        self.assertIn("data-state=\"blocked\"", page)
        self.assertNotIn("data-state=\"passed\"", page)

    def test_arabic_rtl_demo_and_all_eight_roles(self):
        self.complete()
        page = render_dashboard(self.run)
        self.assertIn('lang="ar" dir="rtl"', page)
        self.assertIn("تشغيل تجريبي", page)
        self.assertIn("لا يمنح اعتماد إصدار", page)
        for role in ROLES:
            self.assertIn(f'data-role="{role}"', page)
        self.assertEqual(page.count('class="stage-detail"'), 8)
        self.assertNotIn("data-state=\"passed\"", page)

    def test_missing_stage_never_green_even_when_manifest_completed(self):
        self.complete("live")
        (self.run / "tester.json").unlink()
        self.write("checks.json", {"status": "passed", "checks": [{"name": "unit", "status": "passed", "required": True, "returncode": 0}]})
        page = render_dashboard(self.run)
        self.assertIn("data-state=\"blocked\"", page)
        self.assertIn("غير متاح", page)

    def test_html_and_url_injection_escaped(self):
        self.complete("live")
        self.write("researcher.json", {"role": "researcher", "data": {"summary": '<script>alert(1)</script><img src=x onerror="bad">'}, "evidence_urls": ["javascript:alert(1)", "https://example.org/search?q=\"<script>", "https://safe.example/source", "https://safe.example/\nheader", "//evil.example"]})
        page = render_dashboard(self.run)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn('href="javascript:', page)
        self.assertIn('href="https://safe.example/source"', page)
        self.assertNotIn('href="//evil.example', page)
        self.assertIn('rel="noopener noreferrer"', page)

    def test_escape_and_symlink_paths_not_read(self):
        outside = Path(self.tmp.name) / "outside.json"
        outside.write_text(json.dumps({"role": "researcher", "data": {"summary": "SECRET OUTSIDE"}}), encoding="utf-8")
        for name in ("../outside.json", str(outside), "escape.json"):
            if name == "escape.json":
                (self.run / name).symlink_to(outside)
            self.write("manifest.json", {"status": "completed", "mode": "live", "stages": [{"role": "researcher", "artifact": name}]})
            page = render_dashboard(self.run)
            self.assertNotIn("SECRET OUTSIDE", page)
            self.assertIn("data-state=\"blocked\"", page)

    def test_large_files_and_wrong_role_are_unavailable(self):
        self.complete("live")
        (self.run / "researcher.json").write_text(" " * (2 * 1024 * 1024), encoding="utf-8")
        self.write("tester.json", {"role": "planner", "data": {"summary": "WRONG ROLE"}})
        page = render_dashboard(self.run)
        self.assertIn("data-state=\"blocked\"", page)
        self.assertNotIn("WRONG ROLE", page)

    def test_tool_report_exit_status_and_nested_report(self):
        self.complete("live")
        self.write("checks/report.json", {"status": "passed", "checks": [{"name": "Semgrep", "status": "passed", "required": True, "returncode": 2, "argv": ["semgrep", "--config", "auto"], "reason": "<unsafe>"}]})
        page = render_dashboard(self.run)
        self.assertIn("Semgrep", page)
        self.assertIn("رمز الخروج", page)
        self.assertIn("&lt;unsafe&gt;", page)
        self.assertIn("data-state=\"blocked\"", page)
        self.assertIn('class="badge error"', page)

    def test_rejects_nonloopback_bind_before_server_creation(self):
        for host in ("0.0.0.0", "::", "192.168.1.2", "example.com"):
            with self.subTest(host=host), patch("programmed_minds.dashboard.ThreadingHTTPServer") as server:
                with self.assertRaises(ValueError):
                    serve(self.run, host)
                server.assert_not_called()

    def split_run(self, audit_status="verified", mode="live"):
        self.complete(mode)
        manifest = json.loads((self.run / "manifest.json").read_text())
        manifest.update(status="planned", stages=manifest["stages"][:-1])
        self.write("manifest.json", manifest)
        audit = Path(self.tmp.name) / "audit"
        checks = Path(self.tmp.name) / "checks"
        audit.mkdir()
        checks.mkdir()
        report = {"status": "passed", "checks": [{"name": "python-tests", "status": "passed", "required": True, "returncode": 0}]}
        (checks / "checks.json").write_text(json.dumps(report), encoding="utf-8")
        (audit / "01-tester.json").write_text(json.dumps({"role": "tester", "data": {"verdict": "pass"}, "identity": "live/tester"}), encoding="utf-8")
        audit_manifest = {"status": audit_status, "mode": mode, "planned_run": str(self.run), "report_hash": hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False).encode()).hexdigest(), "stages": [{"role": "tester", "artifact": "01-tester.json"}], "reasons": [] if audit_status == "verified" else ["<blocked audit>"]}
        (audit / "manifest.json").write_text(json.dumps(audit_manifest), encoding="utf-8")
        return audit, checks

    def test_explicit_plan_audit_and_checks_roots_combine_actual_outputs(self):
        audit, checks = self.split_run()
        page = render_dashboard(self.run, audit_dir=audit, checks_dir=checks)
        self.assertIn('data-state="verified"', page)
        self.assertIn("التخطيط مكتمل", page)
        self.assertIn("التدقيق موثّق", page)
        self.assertIn("live/tester", page)
        self.assertIn("python-tests", page)

    def test_blocked_audit_and_audit_alone_never_complete(self):
        audit, checks = self.split_run("blocked")
        page = render_dashboard(self.run, audit_dir=audit, checks_dir=checks)
        self.assertIn('data-state="blocked"', page)
        self.assertIn("&lt;blocked audit&gt;", page)
        page = render_dashboard(audit, checks_dir=checks)
        self.assertIn("live/tester", page)
        self.assertIn('data-state="blocked"', page)
        self.assertNotIn('data-state="verified"', page)

    def test_manifest_cross_root_references_are_not_followed_and_demo_blocks(self):
        audit, checks = self.split_run(mode="demo")
        other = Path(self.tmp.name) / "secret.json"
        other.write_text('{"brief":"SECRET CROSS ROOT"}', encoding="utf-8")
        audit_manifest = json.loads((audit / "manifest.json").read_text())
        audit_manifest["planned_run"] = str(other)
        audit_manifest["checks"] = str(checks)
        (audit / "manifest.json").write_text(json.dumps(audit_manifest), encoding="utf-8")
        page = render_dashboard(audit)
        self.assertNotIn("SECRET CROSS ROOT", page)
        self.assertNotIn("python-tests", page)
        page = render_dashboard(self.run, audit_dir=audit, checks_dir=checks)
        self.assertIn('data-state="blocked"', page)
        self.assertNotIn('data-state="verified"', page)

    def test_http_only_serves_root_and_does_not_allow_writes(self):
        self.complete()
        started = queue.Queue()

        class TestServer(ThreadingHTTPServer):
            def serve_forever(self):
                started.put(self)
                super().serve_forever(poll_interval=0.01)

        with patch("programmed_minds.dashboard.ThreadingHTTPServer", TestServer):
            worker = threading.Thread(target=serve, args=(self.run, "127.0.0.1", 0), daemon=True)
            worker.start()
            server = started.get(timeout=5)
            try:
                for method, route, expected in (("GET", "/", 200), ("GET", "/manifest.json", 404), ("GET", "/../outside.json", 404), ("POST", "/", 501)):
                    with self.subTest(method=method, route=route):
                        client = http.client.HTTPConnection(*server.server_address, timeout=5)
                        try:
                            client.request(method, route)
                            response = client.getresponse()
                            self.assertEqual(response.status, expected)
                            if expected == 200:
                                self.assertIn("default-src 'none'", response.getheader("Content-Security-Policy"))
                                self.assertIn(b'<html lang="ar" dir="rtl">', response.read())
                            else:
                                response.read()
                        finally:
                            client.close()
                client = http.client.HTTPConnection(*server.server_address, timeout=5)
                try:
                    client.request("GET", "/", headers={"Host": "attacker.example"})
                    response = client.getresponse()
                    self.assertEqual(response.status, 403)
                    response.read()
                finally:
                    client.close()
            finally:
                server.shutdown()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive())


if __name__ == "__main__":
    unittest.main()
