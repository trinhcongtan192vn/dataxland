{{ config(enabled='tiktok_shop_file' in var('sources', [])) }}
{#- Đơn từ file của lượt kiểm tra sức khỏe (spec 07 §4). -#}
{{ dx_file_orders('tiktok_shop_file', 'tiktok_shop') }}
