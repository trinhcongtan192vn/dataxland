{{ config(enabled='shopee_file' in var('sources', [])) }}
{{ dx_file_order_lines('shopee_file') }}
