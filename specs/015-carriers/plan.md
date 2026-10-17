# Implementation Plan: Hãng vận chuyển

**Branch**: `015-carriers` | **Spec**: [spec.md](spec.md)

- Postgres `carrier_events`, `carrier_files` (Alembic `0003`); router `carriers.py` (webhook, `/v1/carriers`, tải file).
- Connector `pipelines/connectors/carriers/{ghn,ghtk,jnt}.py`; mẫu `jnt_reconcile` trong `signatures.yml`.
- dbt: hợp đồng `shipments` (sinh từ `gen_staging_yml.py`), macro `dx_carrier_staging`, seed `shipment_status_map`, `int_union__shipments`, `fct_shipment`, `mrt_seller__shipments`.
- Semantic: `requires: carrier`, chiều `carrier`, `shipment_status`, ba chỉ số.
- Web `/app/inputs/carriers`; hướng dẫn `knowledge/integrations/{ghn,ghtk,jnt}.md`.

Quyết định: ADR 0005, ADR 0002 #57–#58.
