-- T5015: PII encryption at rest — encrypted_value column + envelope storage
--
-- Adds a generic envelope-encrypted column scheme so PII fields across
-- every PII-bearing table can be stored as opaque ciphertext produced by
-- backend/compliance/pii_encrypt.py (Fernet DEK wrapped by KMS KEK).
--
-- Strategy:
--   * Each PII column keeps its existing name but stores the Fernet token
--     string ("v1:<key_id>:<token>"). Text columns already accommodate this.
--   * A central `pii_encrypted_values` table records (table, column, row id,
--     dek_id, wrapped_dek, created_at) so ciphertext is portable and DEK
--     rotation can re-wrap without touching the business tables.
--   * A `kms_dek_registry` table persists wrapped DEKs + rotation state so
--     the in-process KMSManager can hydrate across restarts.
--
-- RLS: service_role + admin/compliance only. Candidates/users never read
-- the envelope table directly.

BEGIN;

-- ----------------------------------------------------------------------
-- 1. KMS DEK registry (persisted wrapped DEKs)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.kms_dek_registry (
  key_id text PRIMARY KEY,
  provider text NOT NULL DEFAULT 'local',
  wrapped_dek text NOT NULL,           -- KEK-encrypted DEK (portable)
  state text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'retired', 'revoked')),
  created_at timestamptz NOT NULL DEFAULT now(),
  rotated_at timestamptz,
  expires_at timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
  tenant_id uuid
);

COMMENT ON TABLE public.kms_dek_registry IS
  'T5015 — KMS Data Encryption Key registry. wrapped_dek is the KEK-encrypted form; plaintext DEK never persisted.';

CREATE INDEX IF NOT EXISTS idx_kms_dek_registry_state
  ON public.kms_dek_registry (state);
CREATE INDEX IF NOT EXISTS idx_kms_dek_registry_expires
  ON public.kms_dek_registry (expires_at);

-- ----------------------------------------------------------------------
-- 2. Central encrypted-value ledger
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pii_encrypted_values (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  table_name text NOT NULL,
  column_name text NOT NULL,
  row_id text NOT NULL,                -- PK of the business row (cast to text)
  dek_id text NOT NULL REFERENCES public.kms_dek_registry(key_id) ON DELETE RESTRICT,
  envelope_version text NOT NULL DEFAULT 'v1',
  ciphertext_hash text NOT NULL,       -- sha256 of the envelope token (lookup)
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  tenant_id uuid
);

CREATE INDEX IF NOT EXISTS idx_pii_enc_values_lookup
  ON public.pii_encrypted_values (table_name, column_name, row_id);
CREATE INDEX IF NOT EXISTS idx_pii_enc_values_hash
  ON public.pii_encrypted_values (ciphertext_hash);
CREATE INDEX IF NOT EXISTS idx_pii_enc_values_dek
  ON public.pii_encrypted_values (dek_id);

COMMENT ON TABLE public.pii_encrypted_values IS
  'T5015 — ledger mapping every encrypted PII cell to its wrapping DEK, enabling rotation + portability.';

-- ----------------------------------------------------------------------
-- 3. RLS
-- ----------------------------------------------------------------------
ALTER TABLE public.kms_dek_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pii_encrypted_values ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS kms_dek_service ON public.kms_dek_registry;
CREATE POLICY kms_dek_service ON public.kms_dek_registry
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS kms_dek_admin ON public.kms_dek_registry;
CREATE POLICY kms_dek_admin ON public.kms_dek_registry
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.user_profiles up
      WHERE up.id = auth.uid() AND up.role IN ('admin', 'compliance')
    )
  );

DROP POLICY IF EXISTS pii_enc_values_service ON public.pii_encrypted_values;
CREATE POLICY pii_enc_values_service ON public.pii_encrypted_values
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS pii_enc_values_admin ON public.pii_encrypted_values;
CREATE POLICY pii_enc_values_admin ON public.pii_encrypted_values
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.user_profiles up
      WHERE up.id = auth.uid() AND up.role IN ('admin', 'compliance')
    )
  );

-- ----------------------------------------------------------------------
-- 4. updated_at trigger for pii_encrypted_values
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.touch_pii_encrypted_values()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_touch_pii_encrypted_values ON public.pii_encrypted_values;
CREATE TRIGGER trg_touch_pii_encrypted_values
  BEFORE UPDATE ON public.pii_encrypted_values
  FOR EACH ROW EXECUTE FUNCTION public.touch_pii_encrypted_values();

-- ----------------------------------------------------------------------
-- 5. Index hot path for PII columns (helps equality lookups on ciphertext
--    where the app stores the token directly in the business column).
-- ----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_users_email_token
  ON public.users (email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_phone_token
  ON public.users (phone) WHERE phone IS NOT NULL;

COMMIT;
