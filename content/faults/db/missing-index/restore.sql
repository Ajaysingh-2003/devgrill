CREATE INDEX IF NOT EXISTS orders_user_id_created_at_idx ON orders (user_id, created_at DESC);
