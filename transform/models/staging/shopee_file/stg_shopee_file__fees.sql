{{ config(enabled='shopee_file' in var('sources', [])) }}
{{ dx_file_fees('shopee_file', 'shopee') }}
