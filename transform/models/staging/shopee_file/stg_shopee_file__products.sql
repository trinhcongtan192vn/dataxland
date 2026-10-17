{{ config(enabled='shopee_file' in var('sources', [])) }}
{{ dx_file_products('shopee_file') }}
