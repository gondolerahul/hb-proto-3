-- =============================================================================
-- selective_clean_db.sql
-- Selective Database Cleanup Script — HireBuddha Proto-3
-- =============================================================================
-- PURPOSE:
--   Selectively deletes data from the database while preserving specific
--   companies, users, and entity library records needed for the application.
--
-- PRESERVED (Platform Hub):
--   • APP company "HireBuddha" (always preserved — root of the company tree)
--   • Partner company "Durwankur Technologies*" + its users (matched by prefix)
--   • Tenants: "Fortune", "GoChillaao", "Evaworld"
--   • Users: "HireBuddha Admin", "Saurabh", "Admin Go Chillao",
--            "admin fortune", "Shrirang"
--
-- PRESERVED (Entity Library):
--   • Process "doc-factory-process" + all its descendant entities
--   • Agents: children of "doc-factory-process", "Karuna", "VoiceBot",
--             "MetaAgent" + its children, "Priya"
--   • Skills & Actions: children of "doc-factory-process",
--                       children of "MetaAgent"
--
-- DELETED:
--   • All other partner companies + their users
--   • All other tenants
--   • All other users
--   • All other entity library records
--   • ALL execution runs (no exceptions)
--   • Company-scoped data (billing, sessions, etc.) for removed companies
--
-- UNTOUCHED:
--   • subscription_tiers, tool_registry_entries, hitl_checkpoint_defs
--   • phone_numbers (inventory)
--   • integration_registry, model_task_defaults (for surviving companies)
--   • billing_config, credit_wallets (for surviving companies)
--
-- USAGE:
--   PGPASSWORD=postgres psql -U postgres -h localhost -p 5433 -d hirebuddha \
--       -f db-scripts/selective_clean_db.sql
--
-- CAUTION:
--   ⚠️  This is IRREVERSIBLE. Take a database backup before running.
--   ⚠️  Designed for development / staging environments only.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- PHASE 0: Pre-flight — Validate that kept records exist
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    _cnt INTEGER;
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE '  PHASE 0: Pre-flight validation';
    RAISE NOTICE '============================================================';

    -- Check APP company "HireBuddha" exists
    SELECT COUNT(*) INTO _cnt FROM companies WHERE name = 'HireBuddha' AND type = 'APP';
    IF _cnt = 0 THEN RAISE WARNING 'APP company "HireBuddha" NOT FOUND — script may not work as expected';
    ELSE RAISE NOTICE '  ✓ APP company "HireBuddha" found';
    END IF;

    -- Check partner company "Durwankur Technologies" (may have suffix)
    SELECT COUNT(*) INTO _cnt FROM companies WHERE name LIKE 'Durwankur Technologies%' AND type = 'PARTNER';
    IF _cnt = 0 THEN RAISE WARNING 'Partner company "Durwankur Technologies" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ Partner company "Durwankur Technologies" found';
    END IF;

    -- Check tenants
    SELECT COUNT(*) INTO _cnt FROM companies WHERE name = 'Fortune' AND type = 'TENANT';
    IF _cnt = 0 THEN RAISE WARNING 'Tenant "Fortune" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ Tenant "Fortune" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM companies WHERE name = 'GoChillaao' AND type = 'TENANT';
    IF _cnt = 0 THEN RAISE WARNING 'Tenant "GoChillaao" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ Tenant "GoChillaao" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM companies WHERE name = 'Evaworld' AND type = 'TENANT';
    IF _cnt = 0 THEN RAISE WARNING 'Tenant "Evaworld" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ Tenant "Evaworld" found';
    END IF;

    -- Check users
    SELECT COUNT(*) INTO _cnt FROM users WHERE full_name = 'HireBuddha Admin';
    IF _cnt = 0 THEN RAISE WARNING 'User "HireBuddha Admin" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ User "HireBuddha Admin" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM users WHERE full_name = 'Saurabh';
    IF _cnt = 0 THEN RAISE WARNING 'User "Saurabh" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ User "Saurabh" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM users WHERE full_name = 'Admin Go Chillao';
    IF _cnt = 0 THEN RAISE WARNING 'User "Admin Go Chillao" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ User "Admin Go Chillao" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM users WHERE full_name = 'admin fortune';
    IF _cnt = 0 THEN RAISE WARNING 'User "admin fortune" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ User "admin fortune" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM users WHERE full_name = 'Shrirang';
    IF _cnt = 0 THEN RAISE WARNING 'User "Shrirang" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ User "Shrirang" found';
    END IF;

    -- Check entity library records
    SELECT COUNT(*) INTO _cnt FROM hierarchical_entities WHERE name = 'doc-factory-process' AND type = 'PROCESS';
    IF _cnt = 0 THEN RAISE WARNING 'Process "doc-factory-process" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ Process "doc-factory-process" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM hierarchical_entities WHERE name = 'MetaAgent' AND type = 'AGENT';
    IF _cnt = 0 THEN RAISE WARNING 'Agent "MetaAgent" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ Agent "MetaAgent" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM hierarchical_entities WHERE name = 'Karuna' AND type = 'AGENT';
    IF _cnt = 0 THEN RAISE WARNING 'Agent "Karuna" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ Agent "Karuna" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM hierarchical_entities WHERE name = 'VoiceBot' AND type = 'AGENT';
    IF _cnt = 0 THEN RAISE WARNING 'Agent "VoiceBot" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ Agent "VoiceBot" found';
    END IF;

    SELECT COUNT(*) INTO _cnt FROM hierarchical_entities WHERE name = 'Priya' AND type = 'AGENT';
    IF _cnt = 0 THEN RAISE WARNING 'Agent "Priya" NOT FOUND';
    ELSE RAISE NOTICE '  ✓ Agent "Priya" found';
    END IF;

    RAISE NOTICE '  Pre-flight complete.';
    RAISE NOTICE '';
END;
$$;


-- ---------------------------------------------------------------------------
-- PHASE 1: Build temp tables of IDs to KEEP
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE '  PHASE 1: Building keep-lists';
    RAISE NOTICE '============================================================';
END;
$$;

-- 1a. Companies to KEEP
-- Start with explicitly named companies, then add parent companies of kept
-- tenants (to prevent FK violations on the self-referencing parent_id).
DROP TABLE IF EXISTS _keep_companies;
CREATE TEMP TABLE _keep_companies AS
SELECT id FROM companies WHERE
    -- APP company (root)
    (name = 'HireBuddha' AND type = 'APP')
    -- Partner to keep (may have suffix like "(Sales & Marketing)")
    OR (name LIKE 'Durwankur Technologies%' AND type = 'PARTNER')
    -- Tenants to keep
    OR (name = 'Fortune' AND type = 'TENANT')
    OR (name = 'GoChillaao' AND type = 'TENANT')
    OR (name = 'Evaworld' AND type = 'TENANT')
;

-- Also include parent companies of kept tenants (self-referencing FK safety)
INSERT INTO _keep_companies (id)
SELECT DISTINCT c.parent_id
FROM companies c
WHERE c.id IN (SELECT id FROM _keep_companies)
AND c.parent_id IS NOT NULL
AND c.parent_id NOT IN (SELECT id FROM _keep_companies);

DO $$
DECLARE _cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO _cnt FROM _keep_companies;
    RAISE NOTICE '  Companies to KEEP: %', _cnt;
END;
$$;

-- 1b. Users to KEEP
DROP TABLE IF EXISTS _keep_users;
CREATE TEMP TABLE _keep_users AS
SELECT id FROM users WHERE
    full_name IN ('HireBuddha Admin', 'Saurabh', 'Admin Go Chillao', 'admin fortune', 'Shrirang')
;

DO $$
DECLARE _cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO _cnt FROM _keep_users;
    RAISE NOTICE '  Users to KEEP: %', _cnt;
END;
$$;

-- 1c. Entities to KEEP
--
-- Strategy:
--   1. Start with "doc-factory-process" (PROCESS) — keep it + ALL descendants
--   2. Find "MetaAgent" (AGENT) — keep it + ALL its children (skills, actions, etc.)
--   3. Find standalone agents "Karuna", "VoiceBot", "Priya" — keep them
--   4. Collect ALL IDs into a single temp table
--
-- For recursive descendant resolution, we use a CTE that walks parent_id.

DROP TABLE IF EXISTS _keep_entities;
CREATE TEMP TABLE _keep_entities (id UUID PRIMARY KEY);

-- 1c-i. "doc-factory-process" + all descendants (recursive)
INSERT INTO _keep_entities (id)
WITH RECURSIVE entity_tree AS (
    -- Anchor: the doc-factory-process itself
    SELECT id FROM hierarchical_entities
    WHERE name = 'doc-factory-process' AND type = 'PROCESS'
    UNION ALL
    -- Recurse: all children of nodes already in the tree
    SELECT he.id
    FROM hierarchical_entities he
    JOIN entity_tree et ON he.parent_id = et.id
)
SELECT id FROM entity_tree
ON CONFLICT (id) DO NOTHING;

DO $$
DECLARE _cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO _cnt FROM _keep_entities;
    RAISE NOTICE '  Entities after doc-factory-process tree: %', _cnt;
END;
$$;

-- 1c-ii. "MetaAgent" + all its children (recursive)
INSERT INTO _keep_entities (id)
WITH RECURSIVE meta_tree AS (
    SELECT id FROM hierarchical_entities
    WHERE name = 'MetaAgent' AND type = 'AGENT'
    UNION ALL
    SELECT he.id
    FROM hierarchical_entities he
    JOIN meta_tree mt ON he.parent_id = mt.id
)
SELECT id FROM meta_tree
ON CONFLICT (id) DO NOTHING;

DO $$
DECLARE _cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO _cnt FROM _keep_entities;
    RAISE NOTICE '  Entities after MetaAgent tree: %', _cnt;
END;
$$;

-- 1c-iii. Standalone agents: Karuna, VoiceBot, Priya
INSERT INTO _keep_entities (id)
SELECT id FROM hierarchical_entities
WHERE name IN ('Karuna', 'VoiceBot', 'Priya') AND type = 'AGENT'
ON CONFLICT (id) DO NOTHING;

DO $$
DECLARE _cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO _cnt FROM _keep_entities;
    RAISE NOTICE '  Entities to KEEP (final): %', _cnt;
    RAISE NOTICE '';
END;
$$;


-- ---------------------------------------------------------------------------
-- PHASE 2: Delete ALL execution runs and related tables
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    tbl TEXT;
    tbl_exists BOOLEAN;
    del_cnt BIGINT;
    -- Tables to TRUNCATE (leaf → root order for execution data)
    tables_to_truncate TEXT[] := ARRAY[
        'execution_trace_events',
        'wallet_holds',
        'llm_interaction_logs',
        'tool_interaction_logs',
        'human_approvals',
        'usage_logs',
        'episodic_memories',
        'cortex_nodes',
        'cortex_trees',
        'execution_runs'
    ];
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE '  PHASE 2: Delete ALL execution runs + related data';
    RAISE NOTICE '============================================================';

    FOREACH tbl IN ARRAY tables_to_truncate
    LOOP
        SELECT EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'public' AND tablename = tbl
        ) INTO tbl_exists;

        IF tbl_exists THEN
            EXECUTE format('SELECT COUNT(*) FROM %I', tbl) INTO del_cnt;
            EXECUTE format('TRUNCATE TABLE %I RESTART IDENTITY CASCADE', tbl);
            RAISE NOTICE '  TRUNCATED %-35s (% rows removed)', tbl, del_cnt;
        ELSE
            RAISE NOTICE '  SKIPPED   %-35s (table not found)', tbl;
        END IF;
    END LOOP;

    RAISE NOTICE '';
END;
$$;


-- ---------------------------------------------------------------------------
-- PHASE 3: Delete entity library records NOT in keep set
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    del_cnt BIGINT;
    tbl_exists BOOLEAN;
    wave INTEGER := 0;
    wave_cnt BIGINT := 1;
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE '  PHASE 3: Selective entity library cleanup';
    RAISE NOTICE '============================================================';

    -- 3a. Delete documents + chunks linked to entities being removed
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'document_chunks') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM document_chunks
        WHERE document_id IN (
            SELECT id FROM documents
            WHERE entity_id IS NOT NULL
            AND entity_id NOT IN (SELECT id FROM _keep_entities)
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % document_chunks for removed entities', del_cnt;
    END IF;

    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'documents') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM documents
        WHERE entity_id IS NOT NULL
        AND entity_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % documents for removed entities', del_cnt;
    END IF;

    -- 3b. Delete artifacts linked to entities being removed
    -- First delete call_content referencing these artifacts
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'call_content') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM call_content
        WHERE audio_artifact_id IN (
            SELECT id FROM artifacts
            WHERE (agent_id IS NOT NULL AND agent_id NOT IN (SELECT id FROM _keep_entities))
               OR (campaign_id IS NOT NULL AND campaign_id NOT IN (SELECT id FROM _keep_entities))
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % call_content for removed entity artifacts', del_cnt;
    END IF;

    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'artifacts') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM artifacts
        WHERE (agent_id IS NOT NULL AND agent_id NOT IN (SELECT id FROM _keep_entities))
           OR (campaign_id IS NOT NULL AND campaign_id NOT IN (SELECT id FROM _keep_entities));
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % artifacts for removed entities', del_cnt;
    END IF;

    -- 3c. Delete signals referencing removed entities
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'signals') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM signals
        WHERE owner_process_id IS NOT NULL
        AND owner_process_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % signals for removed entities', del_cnt;
    END IF;

    -- 3d. Delete trigger_registry referencing removed entities
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'trigger_registry') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM trigger_registry
        WHERE process_entity_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % trigger_registry entries for removed entities', del_cnt;
    END IF;

    -- 3e. Delete budget_envelopes referencing removed entities
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'budget_envelopes') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM budget_envelopes
        WHERE entity_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % budget_envelopes for removed entities', del_cnt;
    END IF;

    -- 3f. Delete loop_runtime referencing removed entities
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'loop_runtime') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM loop_runtime
        WHERE loop_entity_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % loop_runtime entries for removed entities', del_cnt;
    END IF;

    -- 3g. Delete voice_sessions referencing removed entities
    -- First delete campaign_calls referencing voice_sessions of removed agents
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'campaign_calls') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM campaign_calls
        WHERE voice_session_id IN (
            SELECT id FROM voice_sessions
            WHERE agent_id NOT IN (SELECT id FROM _keep_entities)
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % campaign_calls for removed agent sessions', del_cnt;
    END IF;

    -- Delete lead_queue referencing removed agents
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_queue') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM lead_queue
        WHERE agent_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % lead_queue entries for removed agents', del_cnt;
    END IF;

    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'voice_sessions') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM voice_sessions
        WHERE agent_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % voice_sessions for removed agents', del_cnt;
    END IF;

    -- 3h. Delete whatsapp_sessions referencing removed entities
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'whatsapp_sessions') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM whatsapp_sessions
        WHERE agent_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % whatsapp_sessions for removed agents', del_cnt;
    END IF;

    -- 3i. Delete conversation_history referencing removed entities
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'conversation_history') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM conversation_history
        WHERE agent_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % conversation_history for removed agents', del_cnt;
    END IF;

    -- 3j. Delete campaigns referencing removed entities
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'campaigns') INTO tbl_exists;
    IF tbl_exists THEN
        -- First delete remaining campaign_calls for campaigns of removed agents
        DELETE FROM campaign_calls
        WHERE campaign_id IN (
            SELECT id FROM campaigns
            WHERE agent_id NOT IN (SELECT id FROM _keep_entities)
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % campaign_calls for removed agent campaigns', del_cnt;

        DELETE FROM campaigns
        WHERE agent_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % campaigns for removed agents', del_cnt;
    END IF;

    -- 3k. Delete call_logs referencing removed entities
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'call_logs') INTO tbl_exists;
    IF tbl_exists THEN
        -- Delete call_content first
        DELETE FROM call_content
        WHERE call_log_id IN (
            SELECT id FROM call_logs
            WHERE agent_id IS NOT NULL
            AND agent_id NOT IN (SELECT id FROM _keep_entities)
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % call_content for removed agent call_logs', del_cnt;

        DELETE FROM call_logs
        WHERE agent_id IS NOT NULL
        AND agent_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % call_logs for removed agents', del_cnt;
    END IF;

    -- 3l. Delete phone_numbers assigned to removed entities
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'phone_numbers') INTO tbl_exists;
    IF tbl_exists THEN
        -- Don't delete the phone numbers, just unassign them
        UPDATE phone_numbers
        SET agent_id = NULL,
            customer_id = NULL,
            customer_name = NULL,
            customer_metadata = NULL,
            assigned_at = NULL,
            status = CASE
                WHEN company_id IN (SELECT id FROM _keep_companies) THEN 'claimed'
                ELSE 'available'
            END
        WHERE agent_id IS NOT NULL
        AND agent_id NOT IN (SELECT id FROM _keep_entities);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Unassigned % phone_numbers from removed agents', del_cnt;
    END IF;

    -- 3m. Finally, delete the hierarchical_entities themselves
    -- Must delete children before parents (leaf → root). The self-referencing
    -- FK (parent_id) means we must delete leaves first.
    -- Delete in waves: entities whose children are all either kept or already
    -- deleted. Loop until no more rows are deleted.
    wave := 0;
    wave_cnt := 1;
    WHILE wave_cnt > 0 LOOP
        wave := wave + 1;
        DELETE FROM hierarchical_entities
        WHERE id NOT IN (SELECT id FROM _keep_entities)
        AND id NOT IN (
            -- Has children that are NOT in the keep list and still exist
            SELECT DISTINCT parent_id FROM hierarchical_entities
            WHERE parent_id IS NOT NULL
            AND id NOT IN (SELECT id FROM _keep_entities)
        );
        GET DIAGNOSTICS wave_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % hierarchical_entities (wave %)', wave_cnt, wave;
    END LOOP;

    -- Safety check: any orphaned entities still remaining?
    SELECT COUNT(*) INTO del_cnt
    FROM hierarchical_entities
    WHERE id NOT IN (SELECT id FROM _keep_entities);
    IF del_cnt > 0 THEN
        RAISE WARNING '  ⚠️  % entities remain that should have been deleted (possible circular parent_id refs)', del_cnt;
    ELSE
        RAISE NOTICE '  ✓ All unwanted entities deleted successfully';
    END IF;

    RAISE NOTICE '';
END;
$$;


-- ---------------------------------------------------------------------------
-- PHASE 4: Delete company-scoped data for REMOVED companies
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    del_cnt BIGINT;
    tbl_exists BOOLEAN;
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE '  PHASE 4: Delete company-scoped data for removed companies';
    RAISE NOTICE '============================================================';

    -- 4a. Billing: billing_events
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'billing_events') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM billing_events WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % billing_events', del_cnt;
    END IF;

    -- 4b. Billing: payment_transactions
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'payment_transactions') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM payment_transactions WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % payment_transactions', del_cnt;
    END IF;

    -- 4c. Billing: subscriptions
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'subscriptions') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM subscriptions WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % subscriptions', del_cnt;
    END IF;

    -- 4d. Billing: credit_wallets
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'credit_wallets') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM credit_wallets WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % credit_wallets', del_cnt;
    END IF;

    -- 4e. Billing: billing_config
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'billing_config') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM billing_config
        WHERE company_id IS NOT NULL
        AND company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % billing_config (global default preserved)', del_cnt;
    END IF;

    -- 4f. Social connections
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'social_connections') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM social_connections WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % social_connections', del_cnt;
    END IF;

    -- 4g. Email connections
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'email_connections') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM email_connections WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % email_connections', del_cnt;
    END IF;

    -- 4h. Documents (company-scoped, not already deleted by entity cleanup)
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'document_chunks') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM document_chunks
        WHERE document_id IN (
            SELECT id FROM documents WHERE company_id NOT IN (SELECT id FROM _keep_companies)
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % document_chunks for removed companies', del_cnt;
    END IF;

    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'documents') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM documents WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % documents for removed companies', del_cnt;
    END IF;

    -- 4i. Signals for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'signals') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM signals WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % signals for removed companies', del_cnt;
    END IF;

    -- 4j. Trigger registry for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'trigger_registry') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM trigger_registry WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % trigger_registry for removed companies', del_cnt;
    END IF;

    -- 4k. Budget envelopes & loop runtime for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'budget_envelopes') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM budget_envelopes WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % budget_envelopes for removed companies', del_cnt;
    END IF;

    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'loop_runtime') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM loop_runtime WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % loop_runtime for removed companies', del_cnt;
    END IF;

    -- 4l. Source trust scores for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'source_trust_scores') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM source_trust_scores WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % source_trust_scores for removed companies', del_cnt;
    END IF;

    -- 4m. Voice sessions for removed companies (remaining after entity cleanup)
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'voice_sessions') INTO tbl_exists;
    IF tbl_exists THEN
        -- campaign_calls referencing these sessions first
        DELETE FROM campaign_calls
        WHERE voice_session_id IN (
            SELECT id FROM voice_sessions WHERE company_id NOT IN (SELECT id FROM _keep_companies)
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        IF del_cnt > 0 THEN RAISE NOTICE '  Deleted % campaign_calls for removed company sessions', del_cnt; END IF;

        -- lead_queue referencing these sessions
        SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_queue') INTO tbl_exists;
        IF tbl_exists THEN
            DELETE FROM lead_queue WHERE company_id NOT IN (SELECT id FROM _keep_companies);
            GET DIAGNOSTICS del_cnt = ROW_COUNT;
            IF del_cnt > 0 THEN RAISE NOTICE '  Deleted % lead_queue for removed companies', del_cnt; END IF;
        END IF;

        DELETE FROM voice_sessions WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % voice_sessions for removed companies', del_cnt;
    END IF;

    -- 4n. WhatsApp sessions for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'whatsapp_sessions') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM whatsapp_sessions WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % whatsapp_sessions for removed companies', del_cnt;
    END IF;

    -- 4o. Conversation history for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'conversation_history') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM conversation_history WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % conversation_history for removed companies', del_cnt;
    END IF;

    -- 4p. Campaigns for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'campaigns') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM campaign_calls
        WHERE campaign_id IN (
            SELECT id FROM campaigns WHERE company_id NOT IN (SELECT id FROM _keep_companies)
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        IF del_cnt > 0 THEN RAISE NOTICE '  Deleted % campaign_calls for removed companies', del_cnt; END IF;

        DELETE FROM campaigns WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % campaigns for removed companies', del_cnt;
    END IF;

    -- 4q. Artifacts for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'artifacts') INTO tbl_exists;
    IF tbl_exists THEN
        -- call_content referencing artifacts of removed companies
        DELETE FROM call_content
        WHERE audio_artifact_id IN (
            SELECT id FROM artifacts WHERE company_id NOT IN (SELECT id FROM _keep_companies)
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        IF del_cnt > 0 THEN RAISE NOTICE '  Deleted % call_content for removed company artifacts', del_cnt; END IF;

        DELETE FROM artifacts WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % artifacts for removed companies', del_cnt;
    END IF;

    -- 4r. Call logs for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'call_logs') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM call_content
        WHERE call_log_id IN (
            SELECT id FROM call_logs WHERE company_id NOT IN (SELECT id FROM _keep_companies)
        );
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        IF del_cnt > 0 THEN RAISE NOTICE '  Deleted % call_content for removed company call_logs', del_cnt; END IF;

        DELETE FROM call_logs WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % call_logs for removed companies', del_cnt;
    END IF;

    -- 4s. Integration registry for removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'model_task_defaults') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM model_task_defaults WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % model_task_defaults for removed companies', del_cnt;
    END IF;

    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'integration_registry') INTO tbl_exists;
    IF tbl_exists THEN
        DELETE FROM integration_registry WHERE company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Deleted % integration_registry for removed companies', del_cnt;
    END IF;

    -- 4t. Phone numbers: unclaim numbers owned by removed companies
    SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'phone_numbers') INTO tbl_exists;
    IF tbl_exists THEN
        UPDATE phone_numbers
        SET company_id = NULL,
            claimed_by_user_id = NULL,
            claimed_at = NULL,
            agent_id = NULL,
            customer_id = NULL,
            customer_name = NULL,
            customer_metadata = NULL,
            assigned_at = NULL,
            status = 'available'
        WHERE company_id IS NOT NULL
        AND company_id NOT IN (SELECT id FROM _keep_companies);
        GET DIAGNOSTICS del_cnt = ROW_COUNT;
        RAISE NOTICE '  Unclaimed % phone_numbers from removed companies', del_cnt;
    END IF;

    RAISE NOTICE '';
END;
$$;


-- ---------------------------------------------------------------------------
-- PHASE 5: Delete users & companies not in keep set
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    del_cnt BIGINT;
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE '  PHASE 5: Delete users & companies';
    RAISE NOTICE '============================================================';

    -- 5a. Refresh tokens for removed users
    DELETE FROM refresh_tokens
    WHERE user_id NOT IN (SELECT id FROM _keep_users);
    GET DIAGNOSTICS del_cnt = ROW_COUNT;
    RAISE NOTICE '  Deleted % refresh_tokens', del_cnt;

    -- 5b. Users not in keep list
    DELETE FROM users
    WHERE id NOT IN (SELECT id FROM _keep_users);
    GET DIAGNOSTICS del_cnt = ROW_COUNT;
    RAISE NOTICE '  Deleted % users', del_cnt;

    -- 5c. Companies not in keep list
    -- Delete children (tenants of removed partners) before parents
    DELETE FROM companies
    WHERE id NOT IN (SELECT id FROM _keep_companies)
    AND parent_id IS NOT NULL;
    GET DIAGNOSTICS del_cnt = ROW_COUNT;
    RAISE NOTICE '  Deleted % child companies (tenants of removed partners)', del_cnt;

    DELETE FROM companies
    WHERE id NOT IN (SELECT id FROM _keep_companies);
    GET DIAGNOSTICS del_cnt = ROW_COUNT;
    RAISE NOTICE '  Deleted % remaining companies', del_cnt;

    RAISE NOTICE '';
END;
$$;


-- ---------------------------------------------------------------------------
-- PHASE 6: Verification — report final row counts for all public tables
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    tbl TEXT;
    cnt BIGINT;
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE '  PHASE 6: Verification — Final row counts';
    RAISE NOTICE '============================================================';
    FOR tbl IN
        SELECT tablename
        FROM   pg_tables
        WHERE  schemaname = 'public'
        ORDER  BY tablename
    LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I', tbl) INTO cnt;
        RAISE NOTICE '  %-40s → % rows', tbl, cnt;
    END LOOP;
    RAISE NOTICE '============================================================';
END;
$$;

-- Cleanup temp tables
DROP TABLE IF EXISTS _keep_companies;
DROP TABLE IF EXISTS _keep_users;
DROP TABLE IF EXISTS _keep_entities;

COMMIT;

-- =============================================================================
-- End of selective_clean_db.sql
-- =============================================================================
