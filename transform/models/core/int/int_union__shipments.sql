{#- Ghép mọi `stg_<hãng>__shipments` đang bật (FR-ING-09). -#}
{{ config(materialized='table') }}

{{ dx_union_enabled('shipments', dx_contract('shipments')) }}
