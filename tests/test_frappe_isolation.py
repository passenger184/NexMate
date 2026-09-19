"""Phase 4A isolated import regression test.

Proves the Frappe app is runtime-self-contained: it can be imported WITHOUT
repo-root `config.py`, `tools/`, or `service/` on PYTHONPATH, simulating a
normal installed-app environment (`bench get-app` + `install-app`).

Fails if the Frappe app regresses to importing repo-root modules.
Does NOT add repo root to sys.path; uses subprocess with isolated path.
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "frappe_app" / "erpnext_ai_copilot"


class FrappeIsolationTest(unittest.TestCase):
    def test_no_repo_root_imports_in_frappe_app(self):
        """Static: Frappe app source must not import config/tools/service."""
        forbidden = ("from tools", "import tools", "from config", "import config",
                     "from service", "import service", "from rag", "import rag",
                     "from orchestrator", "import orchestrator")
        offenders = []
        for py in (APP_DIR).rglob("*.py"):
            if "__pycache__" in str(py):
                continue
            # Only top-level control-plane modules (not doctype stubs which import frappe only)
            text = py.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pat in forbidden:
                    # Allow comments mentioning tools/contracts as mirror reference (not import)
                    if stripped.startswith(("from tools", "import tools", "from config",
                                            "import config", "from service", "import service",
                                            "from rag", "import rag")):
                        offenders.append(f"{py.relative_to(ROOT)}:{stripped}")
                        break
        self.assertEqual(offenders, [], f"Frappe app imports repo-root modules: {offenders}")

    def test_frappe_app_imports_without_repo_root(self):
        """Dynamic: import Frappe modules with repo root absent from sys.path."""
        # Run subprocess with PYTHONPATH=frappe_app only (not repo root),
        # stubbing frappe/requests (normal Frappe dependencies, not repo-root).
        code = (
            "import sys; "
            "sys.path = [p for p in sys.path if 'ERPNext-AI' not in p]; "
            "import sys as _s; _s.path.insert(0, 'frappe_app'); "
            "import types; "
            "frappe_stub = types.ModuleType('frappe'); "
            "frappe_stub.session = types.SimpleNamespace(user='Administrator'); "
            "frappe_stub.local = types.SimpleNamespace(site='test_site'); "
            "frappe_stub.conf = {}; "
            "frappe_stub.get_roles = lambda u: ['System Manager']; "
            "frappe_stub.has_permission = lambda *a, **k: True; "
            "frappe_stub.get_app_path = lambda *a, **k: 'frappe_app/erpnext_ai_copilot'; "
            "frappe_stub.get_site_path = lambda *a, **k: '/tmp/nexmate_test_site/private/files/nexmate_durable'; "
            "frappe_stub.whitelist = lambda *a, **k: (lambda fn: fn); "
            "frappe_stub.throw = lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg)); "
            "frappe_stub.PermissionError = PermissionError; "
            "frappe_stub.DoesNotExistError = Exception; "
            "frappe_stub.new_doc = lambda *a, **k: None; "
            "frappe_stub.get_doc = lambda *a, **k: None; "
            "frappe_stub.get_all = lambda *a, **k: []; "
            "frappe_stub.db = types.SimpleNamespace(sql=lambda *a, **k: []); "
            "req_stub = types.ModuleType('requests'); "
            "req_stub.Session = object; "
            "_s.modules['frappe'] = frappe_stub; _s.modules['requests'] = req_stub; "
            "import erpnext_ai_copilot.proposals as P; "
            "import erpnext_ai_copilot.audit as A; "
            "print('proposals:', P.TOOL_PROPOSAL_DOCTYPE); "
            "print('audit:', A.AUDIT_DOCTYPE); "
            "print('hash:', P._payload_hash('code_edit','t','p','d','r',{},'s')[:8]); "
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in __import__("os").environ.items() if k not in ("PYTHONPATH",)},
        )
        self.assertEqual(proc.returncode, 0, f"Isolated import failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
        self.assertIn("proposals: NexMate Tool Proposal", proc.stdout)
        self.assertIn("audit: NexMate Audit Entry", proc.stdout)

    def test_packaging_metadata(self):
        """Frappe app metadata structurally correct (hooks/pyproject/modules)."""
        import ast, tomllib
        hooks_text = (APP_DIR / "hooks.py").read_text(encoding="utf-8")
        tree = ast.parse(hooks_text)
        assigned = {n.targets[0].id for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}
        for required in ("app_name", "app_title", "app_publisher", "app_description", "app_email", "app_license"):
            self.assertIn(required, assigned)
        pyproject = (ROOT / "frappe_app" / "pyproject.toml")
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["name"], "erpnext_ai_copilot")
        # All runtime modules present
        for mod in ("api.py", "proposals.py", "audit.py", "debug.py", "conversations.py", "boot.py", "hooks.py"):
            self.assertTrue((APP_DIR / mod).exists(), f"missing {mod}")
        # DocTypes present
        base = APP_DIR / "erpnext_ai_copilot" / "doctype"
        for dt in ("nexmate_tool_proposal", "nexmate_audit_entry", "nexmate_conversation", "nexmate_conversation_turn"):
            self.assertTrue((base / dt / f"{dt}.json").exists())

    def test_inference_boundary_still_works(self):
        """Inference/service side still imports from repo layout (no regression)."""
        from tools.contracts import CONTRACTS, contract_for
        self.assertIn("code_edit", CONTRACTS)
        self.assertIn("business_write", CONTRACTS)
        import config
        self.assertTrue(hasattr(config, "PROJECT_ROOT"))
        # App-local mirror matches inference contract for shared ops
        from frappe_app.erpnext_ai_copilot import proposals as P
        self.assertEqual(set(P.PROPOSAL_STATUSES), set(__import__("tools.contracts", fromlist=["PROPOSAL_STATUSES"]).PROPOSAL_STATUSES))
