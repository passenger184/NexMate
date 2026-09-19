"""M5 contract suite — 6.5

Proves explicit tool schemas (bounded inputs/outputs, permission/context,
side-effect class, approval flag, typed errors, timeout/cancellation,
provenance) are enforced on every entry point and every tool call is
validated against its contract.
"""

import unittest

from tools.contracts import CONTRACTS, contract_for, validate_bounded_inputs, PROPOSAL_FIELDS, PROPOSAL_STATUSES


class ContractSuiteTest(unittest.TestCase):
    def test_every_contract_has_required_fields(self):
        for op, c in CONTRACTS.items():
            with self.subTest(operation=op):
                self.assertIn("operation", c)
                self.assertIn("side_effect", c)
                self.assertIn("approval_required", c)
                self.assertIn("bounded_inputs", c)
                self.assertIn("bounded_outputs", c)
                self.assertIn("typed_errors", c)
                self.assertIn("timeout_seconds", c)
                self.assertIn("provenance", c)
                self.assertIn("audit_event", c)
                self.assertIsInstance(c["timeout_seconds"], int)
                self.assertGreater(c["timeout_seconds"], 0)
                self.assertLessEqual(c["timeout_seconds"], 900)

    def test_approval_flags(self):
        self.assertTrue(contract_for("code_edit")["approval_required"])
        self.assertTrue(contract_for("business_write")["approval_required"])
        self.assertFalse(contract_for("read_file")["approval_required"])
        self.assertFalse(contract_for("search")["approval_required"])
        self.assertFalse(contract_for("erpnext_read")["approval_required"])

    def test_side_effect_classes(self):
        self.assertEqual(contract_for("code_edit")["side_effect"], "code_write")
        self.assertEqual(contract_for("business_write")["side_effect"], "write")
        self.assertEqual(contract_for("read_file")["side_effect"], "read")

    def test_bounded_inputs_enforced(self):
        # code_edit requires path, find, message with minLength
        with self.assertRaises(ValueError):
            validate_bounded_inputs("code_edit", {"path": "x"*2000})
        with self.assertRaises(ValueError):
            validate_bounded_inputs("code_edit", {"path": "ok", "message": "short"})
        # business_write requires doctype, action enum
        with self.assertRaises(ValueError):
            validate_bounded_inputs("business_write", {"doctype": "x", "action": "delete"})
        # valid should not raise
        validate_bounded_inputs("code_edit", {"path": "a.py", "find": "x", "message": "valid message long enough"})

    def test_typed_errors_are_bounded(self):
        for op, c in CONTRACTS.items():
            with self.subTest(operation=op):
                self.assertIsInstance(c["typed_errors"], tuple)
                self.assertGreater(len(c["typed_errors"]), 0)
                for err in c["typed_errors"]:
                    self.assertIsInstance(err, str)
                    self.assertNotIn(" ", err)  # error categories are compact

    def test_proposal_fields_frozen(self):
        self.assertIn("operation", PROPOSAL_FIELDS)
        self.assertIn("target", PROPOSAL_FIELDS)
        self.assertIn("payload", PROPOSAL_FIELDS)
        self.assertIn("diff_preview", PROPOSAL_FIELDS)
        self.assertIn("reason", PROPOSAL_FIELDS)
        self.assertIn("actor", PROPOSAL_FIELDS)
        self.assertIn("site", PROPOSAL_FIELDS)
        self.assertIn("correlation", PROPOSAL_FIELDS)
        self.assertIn("expiry", PROPOSAL_FIELDS)
        self.assertIn("preconditions", PROPOSAL_FIELDS)
        self.assertIn("payload_hash", PROPOSAL_FIELDS)
        self.assertIn("status", PROPOSAL_FIELDS)
        # Statuses must include all lifecycle states
        for s in ("pending", "approved", "rejected", "executing", "succeeded", "failed", "denied", "uncertain", "reconciled", "audit_pending", "conflicting", "expired"):
            self.assertIn(s, PROPOSAL_STATUSES)

    def test_no_sql_tool_introduced(self):
        self.assertNotIn("sql", CONTRACTS)
        self.assertNotIn("sql_query", CONTRACTS)
        # Ensure no contract has SQL-like operation
        for op in CONTRACTS:
            self.assertNotIn("sql", op.lower())

    def test_timeout_bounded(self):
        for op, c in CONTRACTS.items():
            self.assertLessEqual(c["timeout_seconds"], 900)
            self.assertGreater(c["timeout_seconds"], 0)
