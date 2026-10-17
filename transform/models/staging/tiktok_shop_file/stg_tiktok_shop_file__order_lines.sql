{{ config(enabled='tiktok_shop_file' in var('sources', [])) }}
{{ dx_file_order_lines('tiktok_shop_file') }}
