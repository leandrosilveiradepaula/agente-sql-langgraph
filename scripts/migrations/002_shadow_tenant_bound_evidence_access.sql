-- P3: security boundary for the Shadow evidence archive in the DEMO project.
-- This migration intentionally creates no LOGIN credential, tenant binding, or DSN cutover.
-- Source evidence (200 rows) remains unchanged. The existing public table is left intact.
-- Runtime reads/writes require a later, explicitly approved, tenant-bound login.
--
-- Provisioning contract for each approved tenant (later gate):
--  * create a separate LOGIN role, member of langgraph_shadow,
--  * INSERT a private role_name -> organization_id binding,
--  * deploy the identical LANGGRAPH_EXPECTED_ORGANIZATION_ID value,
--  * exercise SELECT/INSERT/UPDATE tests without using the old unscoped records.
-- Never use user-controlled session GUCs as the security boundary.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'langgraph_shadow') THEN
    RAISE EXCEPTION 'LANGGRAPH_SHADOW_ROLE_ALREADY_EXISTS';
  END IF;
  IF to_regclass('public.langgraph_shadow_runs') IS NULL THEN
    RAISE EXCEPTION 'LANGGRAPH_SHADOW_ARCHIVE_MISSING';
  END IF;
END;
$$;

CREATE ROLE langgraph_shadow NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS;

CREATE SCHEMA langgraph_internal AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA langgraph_internal FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE langgraph_internal.shadow_role_tenants (
  role_name name PRIMARY KEY,
  organization_id text NOT NULL CHECK (
    organization_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
  )
);

ALTER TABLE langgraph_internal.shadow_role_tenants ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON langgraph_internal.shadow_role_tenants
  FROM PUBLIC, anon, authenticated, service_role;

GRANT USAGE ON SCHEMA langgraph_internal TO langgraph_shadow;
GRANT SELECT ON langgraph_internal.shadow_role_tenants TO langgraph_shadow;

-- A login can view ONLY its own immutable server-side tenant binding.
-- session_user cannot be substituted by setting a user-controlled GUC.
CREATE POLICY shadow_role_tenants_self_select
  ON langgraph_internal.shadow_role_tenants
  FOR SELECT TO langgraph_shadow
  USING (role_name::text = session_user::text);

REVOKE ALL ON public.langgraph_shadow_runs
  FROM PUBLIC, anon, authenticated, service_role, finance_g1_readonly;
ALTER TABLE public.langgraph_shadow_runs ENABLE ROW LEVEL SECURITY;

-- The base role is NOLOGIN; a future tenant-specific member receives only
-- the Shadow evidence operations needed by PostgresShadowEvidenceRepository.
GRANT USAGE ON SCHEMA public TO langgraph_shadow;
GRANT SELECT, INSERT, UPDATE ON public.langgraph_shadow_runs TO langgraph_shadow;

-- Use the *database-authenticated* login identity to choose the tenant,
-- not request text, JWT, user-settable application variables or LLM output.
CREATE POLICY shadow_runtime_select
  ON public.langgraph_shadow_runs FOR SELECT TO langgraph_shadow
  USING (
    EXISTS (
      SELECT 1 FROM langgraph_internal.shadow_role_tenants binding
      WHERE binding.role_name::text = session_user::text
        AND binding.organization_id = principal ->> 'organization_id'
    )
  );

CREATE POLICY shadow_runtime_insert
  ON public.langgraph_shadow_runs FOR INSERT TO langgraph_shadow
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM langgraph_internal.shadow_role_tenants binding
      WHERE binding.role_name::text = session_user::text
        AND binding.organization_id = principal ->> 'organization_id'
    )
  );

CREATE POLICY shadow_runtime_update
  ON public.langgraph_shadow_runs FOR UPDATE TO langgraph_shadow
  USING (
    EXISTS (
      SELECT 1 FROM langgraph_internal.shadow_role_tenants binding
      WHERE binding.role_name::text = session_user::text
        AND binding.organization_id = principal ->> 'organization_id'
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM langgraph_internal.shadow_role_tenants binding
      WHERE binding.role_name::text = session_user::text
        AND binding.organization_id = principal ->> 'organization_id'
    )
  );

COMMENT ON TABLE langgraph_internal.shadow_role_tenants IS
  'Tenant binding owned by database administrators. Only the bound login can see its own row. No tenant is inferred from historical records.';
COMMENT ON ROLE langgraph_shadow IS
  'NOLOGIN evidence privileges shared by future tenant-specific runtime login identities; RLS always restricts via session_user.';
