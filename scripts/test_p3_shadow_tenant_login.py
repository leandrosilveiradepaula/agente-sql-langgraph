"""Offline tests for gated Shadow login rollout; no database connection."""
import importlib.util
import unittest
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).resolve().parent / "operations" / "p3_shadow_tenant_login.py"
spec = importlib.util.spec_from_file_location("p3_shadow_tenant_login", SCRIPT)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ShadowLoginSafetyTests(unittest.TestCase):
    def test_same_organization_is_deterministic(self):
        self.assertEqual(m.login_role_for("tenant.alpha"), m.login_role_for("tenant.alpha"))
        self.assertNotEqual(m.login_role_for("tenant.alpha"), m.login_role_for("tenant.beta"))
        self.assertLess(len(m.login_role_for("tenant.alpha")), 63)

    def test_tenant_identifier_rejects_untrusted_input(self):
        for bad in ("", "../tenant", " space", "abc'--", "Áç", "a" * 129):
            with self.subTest(bad=bad), self.assertRaises(m.ProvisionBlocked):
                m.login_role_for(bad)

    def test_project_identifier_rejects_other_shape(self):
        with self.assertRaises(m.ProvisionBlocked):
            m.validate_project_and_org("not-a-valid-ref", "tenant")
        m.validate_project_and_org("cenhadslwxgykqtuobgc", "synthetic-tenant")

    def test_pooler_dsn_role_is_tenant_bound_no_admin_password(self):
        admin = "postgresql://postgres.cenhadslwxgykqtuobgc:adminpass@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=verify-full"
        login = m.login_dsn_for(admin, "cenhadslwxgykqtuobgc", "lgshadow_test", "newpass")
        parsed = urlparse(login)
        self.assertEqual(parsed.username, "lgshadow_test.cenhadslwxgykqtuobgc")
        self.assertEqual(parsed.password, "newpass")
        self.assertEqual(parsed.query, "sslmode=verify-full")
        self.assertNotIn("adminpass", login)

    def test_unverified_tls_admin_is_rejected(self):
        admin = "postgresql://postgres.cenhadslwxgykqtuobgc:adminpass@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require"
        with self.assertRaises(Exception):
            m.login_dsn_for(admin, "cenhadslwxgykqtuobgc", "lgshadow_test", "newpass")

    def test_preflight_rejects_untrusted_scope_without_sql(self):
        admin = MagicMock()
        with self.assertRaises(m.ProvisionBlocked):
            m.provision_in_transaction(
                admin, role="invalid", organization_id="synthetic-a", password="x" * 64
            )
        admin.execute.assert_not_called()

    def test_cli_default_has_no_explicit_apply(self):
        source = SCRIPT.read_text()
        self.assertIn('parser.add_argument("--apply", action="store_true")', source)
        self.assertIn('if not args.apply:', source)
        self.assertIn('CREATE-SHADOW-LOGIN', source)
        self.assertIn('P3_DSN_CUTOVER=NOT_PERFORMED', source)
        self.assertNotIn('docker compose up', source)
        self.assertNotIn('ALTER ROLE finance_g1_readonly', source)

    def test_secret_file_is_exclusive(self):
        source = SCRIPT.read_text()
        self.assertIn('os.O_EXCL', source)
        self.assertIn('0o600', source)
        self.assertIn('0o700', source)
        self.assertIn('lstat()', source)


if __name__ == "__main__":
    unittest.main()
