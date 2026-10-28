"""Offline guardrails for the tenant-bound Shadow evidence migration."""
from pathlib import Path
import unittest

SQL_PATH = Path(__file__).resolve().parent / "migrations" / "002_shadow_tenant_bound_evidence_access.sql"


class ShadowRoleTenantMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SQL_PATH.read_text(encoding="utf-8")

    def test_base_role_has_no_login_or_admin_rights(self):
        self.assertIn("CREATE ROLE langgraph_shadow NOLOGIN NOINHERIT NOSUPERUSER", self.text)
        self.assertIn("NOCREATEROLE NOREPLICATION NOBYPASSRLS", self.text)

    def test_source_and_historical_records_are_never_modified(self):
        self.assertNotIn("DELETE FROM public.langgraph_shadow_runs", self.text)
        self.assertNotIn("UPDATE public.langgraph_shadow_runs", self.text)
        self.assertNotIn("INSERT INTO public.langgraph_shadow_runs", self.text)

    def test_database_bound_tenant_and_no_untrusted_guc(self):
        self.assertIn("binding.role_name::text = session_user::text", self.text)
        self.assertIn("binding.organization_id = principal ->> 'organization_id'", self.text)
        self.assertNotIn("current_setting(", self.text)

    def test_all_three_row_operations_are_tenant_scoped(self):
        for action in ("SELECT", "INSERT", "UPDATE"):
            self.assertIn(f"FOR {action} TO langgraph_shadow", self.text)
        self.assertIn("FOR UPDATE TO langgraph_shadow", self.text)
        self.assertIn("WITH CHECK", self.text)

    def test_public_api_is_denied(self):
        self.assertIn("FROM PUBLIC, anon, authenticated, service_role, finance_g1_readonly", self.text)
        self.assertIn("ALTER TABLE public.langgraph_shadow_runs ENABLE ROW LEVEL SECURITY", self.text)
        self.assertIn("ALTER TABLE langgraph_internal.shadow_role_tenants ENABLE ROW LEVEL SECURITY", self.text)

    def test_does_not_provision_login_or_switch_runtime(self):
        self.assertNotIn("CREATE ROLE langgraph_shadow LOGIN", self.text)
        self.assertNotIn("LANGGRAPH_SHADOW_DATABASE_DSN=", self.text)
        self.assertNotIn("INSERT INTO langgraph_internal.shadow_role_tenants", self.text)


if __name__ == "__main__":
    unittest.main()
