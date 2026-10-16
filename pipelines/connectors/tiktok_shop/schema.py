"""Cột của bảng raw TikTok Shop (khớp `transform/samples/tiktok_shop`, spec 01 §4)."""

ORDERS = {
    "id": "string",
    "status": "string",
    "create_time": "int",
    "update_time": "int",
    "paid_time": "int",
    "user_id": "string",
    "buyer_email": "string",
    "currency": "string",
    "original_total_product_price": "numeric",
    "platform_discount": "numeric",
    "seller_discount": "numeric",
    "shipping_fee": "numeric",
    "sub_total": "numeric",
    "total_amount": "numeric",
    "recipient_name": "string",
    "recipient_phone_number": "string",
    "recipient_full_address": "string",
}
ORDER_ITEMS = {
    "id": "string",
    "order_id": "string",
    "product_id": "string",
    "product_name": "string",
    "sku_id": "string",
    "sku_name": "string",
    "seller_sku": "string",
    "quantity": "int",
    "original_price": "numeric",
    "sale_price": "numeric",
    "platform_discount": "numeric",
    "seller_discount": "numeric",
}
SETTLEMENTS = {
    "order_id": "string",
    "transaction_id": "string",
    "statement_time": "int",
    "currency": "string",
    "revenue_amount": "numeric",
    "settlement_amount": "numeric",
    "shipping_cost_amount": "numeric",
    "platform_commission_amount": "numeric",
    "transaction_fee_amount": "numeric",
    "affiliate_commission_amount": "numeric",
}
RETURNS = {
    "return_id": "string",
    "order_id": "string",
    "line_item_id": "string",
    "return_type": "string",
    "return_status": "string",
    "return_reason": "string",
    "refund_total": "numeric",
    "return_shipping_fee": "numeric",
    "create_time": "int",
    "update_time": "int",
}
PRODUCTS = {
    "product_id": "string",
    "title": "string",
    "category_name": "string",
    "sku_id": "string",
    "seller_sku": "string",
    "sku_name": "string",
    "barcode": "string",
}
DAILY_TOTALS = {"date": "date", "order_count": "int", "gross_amount": "numeric", "currency": "string"}
