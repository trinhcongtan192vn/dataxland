{{ config(enabled='google_ads_file' in var('sources', [])) }}
{#- Báo cáo quảng cáo từ file của lượt kiểm tra sức khỏe (spec 07 §4). -#}
{{ dx_file_ads('google_ads_file') }}
