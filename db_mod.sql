ALTER TABLE prom_orders ADD COLUMN delivery_commission float8 DEFAULT 0.0;

ALTER TABLE orders_1c ALTER COLUMN key_crm_id TYPE VARCHAR(20) USING key_crm_id::VARCHAR(20);
ALTER TABLE orders_1c ALTER COLUMN parent_id TYPE VARCHAR(20) USING parent_id::VARCHAR(20);

-- ALTER TABLE prom_orders ALTER COLUMN order_id TYPE VARCHAR(20) USING order_id::VARCHAR(20);
-- ALTER TABLE orders_1c ALTER COLUMN key_crm_id TYPE int4 USING key_crm_id::int4;

-- Индекс для key_crm_id
CREATE INDEX idx_orders_1c_key_crm_id ON orders_1c(key_crm_id);

-- Индекс для parent_id
-- CREATE INDEX idx_orders_1c_tracking_code ON orders_1c(tracking_code);

-- Индекс для supplier_id
-- CREATE INDEX idx_orders_1c_supplier_id ON orders_1c(supplier_id);

-- CREATE INDEX idx_prom_orders_order_id ON prom_orders(order_id);