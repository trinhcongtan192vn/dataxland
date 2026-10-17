{{ config(enabled='ghn' in var('sources', [])) }}
{{ dx_carrier_staging('ghn') }}
