DROP INDEX IF EXISTS reviews_product_id_rating_idx;
CREATE INDEX IF NOT EXISTS reviews_product_id_idx ON reviews (product_id);
