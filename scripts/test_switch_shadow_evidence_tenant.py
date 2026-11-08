"""Offline safety gates for the generic Shadow evidence cutover (no network)."""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Minimal stubs let the safety contract run on machines without psycopg.
psycopg = types.ModuleType('psycopg')
psycopg.Error = type('DatabaseError', (Exception,), {})
conninfo = types.ModuleType('psycopg.conninfo')
conninfo.conninfo_to_dict = lambda x: x if isinstance(x, dict) else {}
conninfo.make_conninfo = lambda *args, **kwargs: {}
typesmod = types.ModuleType('psycopg.types')
jsonmod = types.ModuleType('psycopg.types.json')
jsonmod.Jsonb = dict
with patch.dict(sys.modules, {'psycopg':psycopg,'psycopg.conninfo':conninfo,
                              'psycopg.types':typesmod,'psycopg.types.json':jsonmod}):
    spec = importlib.util.spec_from_file_location(
        'cutover', Path(__file__).resolve().parents[1] / 'operations' / 'switch_shadow_evidence_tenant.py'
    )
    cutover = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cutover)


class SafetyTest(unittest.TestCase):
    def test_pooler_never_reuses_old_login(self):
        source = {'host':'aws-0-us-west-2.pooler.supabase.com','user':'finance_readonly.abcdefghijklmnopqrst','dbname':'postgres'}
        self.assertEqual(cutover.validate_target(source,'abcdefghijklmnopqrst','lgshadow_synthetic'),
                         'lgshadow_synthetic.abcdefghijklmnopqrst')

    def test_wrong_project_is_rejected(self):
        source = {'host':'aws-0-us-west-2.pooler.supabase.com','user':'postgres.zzzzzzzzzzzzzzzzzzzz','dbname':'postgres'}
        with self.assertRaises(cutover.SwitchBlocked):
            cutover.validate_target(source,'abcdefghijklmnopqrst','lgshadow_synthetic')

    def test_direct_supabase_role_target(self):
        source={'host':'db.abcdefghijklmnopqrst.supabase.co','user':'readonly','dbname':'postgres'}
        self.assertEqual(cutover.validate_target(source,'abcdefghijklmnopqrst','lgshadow_synthetic'),
                         'lgshadow_synthetic')

    def test_missing_real_sql_gate_is_rejected(self):
        with self.assertRaises(cutover.SwitchBlocked):
            cutover.patched_env(['LANGGRAPH_SHADOW_DATABASE_DSN=old'], 'new','tenant-1')

    def test_real_sql_true_is_rejected(self):
        with self.assertRaises(cutover.SwitchBlocked):
            cutover.patched_env(['LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=true','LANGGRAPH_SHADOW_DATABASE_DSN=old'],
                                'new','tenant-1')

    def test_cross_tenant_pin_drift_is_rejected(self):
        with self.assertRaises(cutover.SwitchBlocked):
            cutover.patched_env(['LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false','LANGGRAPH_SHADOW_DATABASE_DSN=old',
                                'LANGGRAPH_EXPECTED_ORGANIZATION_ID=tenant-A'], 'new','tenant-B')

    def test_duplicate_sensitive_key_is_rejected(self):
        with self.assertRaises(cutover.SwitchBlocked):
            cutover.patched_env(['LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false','LANGGRAPH_SHADOW_DATABASE_DSN=old',
                                'LANGGRAPH_SHADOW_DATABASE_DSN=old2'],'new','tenant-1')

    def test_success_changes_exactly_two_keys(self):
        original=['LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false','LANGGRAPH_SHADOW_DATABASE_DSN=old',
                  'CONTEXT_POSTGRES_DSN=separate','SEMANTIC_AGENT_VERSION=synthetic-v1']
        out=cutover.patched_env(original,'new-uri','tenant-1')
        self.assertIn('LANGGRAPH_SHADOW_DATABASE_DSN=new-uri\n',out)
        self.assertIn('LANGGRAPH_EXPECTED_ORGANIZATION_ID=tenant-1\n',out)
        self.assertIn('CONTEXT_POSTGRES_DSN=separate\n',out)
        self.assertIn('SEMANTIC_AGENT_VERSION=synthetic-v1\n',out)
        self.assertEqual(out.count('LANGGRAPH_SHADOW_DATABASE_DSN='),1)

    def test_wrong_admin_privilege_is_not_assumed(self):
        self.assertNotIn('ALTER ROLE',Path(__file__).resolve().parents[1].joinpath(
            'operations/switch_shadow_evidence_tenant.py').read_text())


if __name__ == '__main__':
    unittest.main()
