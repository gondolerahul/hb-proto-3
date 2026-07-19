# hb-tenant-db — the per-tenant business database (Increment 1 / SCH, §23.4).
#
# A dedicated Postgres + pgvector container per tenant (data plane); the
# control plane keeps identity/billing/registries/runs/signals + KB/memory
# (v3.0.6). Small-footprint config is applied at `docker run` time per tier
# (shared_buffers/max_connections) by TenantDatabaseManager, not baked here.
#
# Go-live (ops, like hb-sandbox): build, `trivy image` scan, push to the prod
# registry, pin the digest in image.pin, then flip TENANT_DB_BACKEND=container.
FROM pgvector/pgvector:pg16

# pgvector ships the extension; a tenant DB CREATEs it on bootstrap if a
# record-level embedding column is ever added (memory itself is control-plane).
LABEL org.hirebuddha.image="hb-tenant-db"
