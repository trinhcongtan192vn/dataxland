{{ config(enabled='tiktok_shop_file' in var('sources', [])) }}
{{ dx_file_products('tiktok_shop_file') }}
