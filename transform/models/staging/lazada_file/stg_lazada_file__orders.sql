{{ config(enabled='lazada_file' in var('sources', [])) }}
{#- Đơn từ file của lượt kiểm tra sức khỏe (spec 07 §4). -#}
{{ dx_file_orders('lazada_file', 'lazada') }}
