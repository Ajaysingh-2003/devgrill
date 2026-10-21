-- ShopKart schema and seed: 18,402 products, 2,000 users, 50,000 orders, 300,000 reviews.
-- Runs once when the Postgres container initialises its data directory.
--
-- Roles (ADR 015). `postgres` is the platform's superuser: its password is random and never
-- leaves the image build, and the platform reaches it only through the container's local
-- socket. The app and the player use `shopkart`, which owns the app's tables (so faults and
-- fixes can add indexes or migrate them) but is not a superuser: it can't reset statistics,
-- drop the stats extension, rewrite catalogs or write files. The verifier reads as `verifier`.
CREATE ROLE shopkart LOGIN PASSWORD 'shopkart';
GRANT USAGE, CREATE ON SCHEMA public TO shopkart;
GRANT pg_read_all_stats TO shopkart;
REVOKE TEMPORARY ON DATABASE shopkart FROM PUBLIC;
GRANT TEMPORARY ON DATABASE shopkart TO shopkart;

-- Everything below until RESET ROLE is created by (and owned by) the app role.
SET ROLE shopkart;


CREATE TABLE products (
    id          integer PRIMARY KEY,
    sku         text NOT NULL UNIQUE,
    name        text NOT NULL,
    description text NOT NULL,
    price_cents integer NOT NULL CHECK (price_cents >= 0),
    stock       integer NOT NULL DEFAULT 100,
    category    text NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id         integer PRIMARY KEY,
    email      text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     integer NOT NULL REFERENCES users(id),
    product_id  integer NOT NULL REFERENCES products(id),
    quantity    integer NOT NULL CHECK (quantity > 0),
    total_cents integer NOT NULL,
    status      text NOT NULL DEFAULT 'pending',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX orders_user_id_created_at_idx ON orders (user_id, created_at DESC);
CREATE INDEX orders_status_idx ON orders (status) WHERE status = 'pending';

INSERT INTO products (id, sku, name, description, price_cents, stock, category)
SELECT g,
       'SKU-' || lpad(g::text, 6, '0'),
       (ARRAY['Trail','Urban','Studio','Classic','Pro','Lite','Max','Mini'])[1 + g % 8] || ' ' ||
       (ARRAY['Backpack','Headphones','Kettle','Sneakers','Jacket','Lamp','Blender','Notebook','Charger','Tent'])[1 + g % 10]
       || ' ' || (g / 80 + 1)::text,
       repeat('Reliable everyday gear with a two-year warranty. ', 3),
       499 + (g * 37) % 19500,
       20 + g % 400,
       (ARRAY['outdoors','audio','kitchen','footwear','clothing','home','office'])[1 + g % 7]
FROM generate_series(1, 18402) AS g;

INSERT INTO users (id, email)
SELECT g, 'user' || g || '@example.test' FROM generate_series(1, 2000) AS g;

INSERT INTO orders (user_id, product_id, quantity, total_cents, status, created_at, updated_at)
SELECT 1 + (g::bigint * 7919) % 2000,
       1 + (g::bigint * 104729) % 18402,
       1 + g % 3,
       (499 + ((1 + (g::bigint * 104729) % 18402) * 37) % 19500) * (1 + g % 3),
       CASE WHEN g % 50 = 0 THEN 'failed' ELSE 'paid' END,
       now() - (g || ' minutes')::interval,
       now() - (g || ' minutes')::interval
FROM generate_series(1, 50000) AS g;

-- Reviews: the rating summary on a product page aggregates them, which makes a product read
-- far from free and is why product reads are cached. Sale products are the most reviewed.
CREATE TABLE reviews (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id integer NOT NULL REFERENCES products(id),
    rating     smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO reviews (product_id, rating, created_at)
SELECT (ARRAY[1042, 1043, 2210, 77, 9001])[1 + g % 5], 1 + (g * 7) % 5, now() - (g || ' seconds')::interval
FROM generate_series(1, 150000) AS g;
INSERT INTO reviews (product_id, rating, created_at)
SELECT 1 + (g::bigint * 7919) % 18402, 1 + g % 5, now() - (g || ' minutes')::interval
FROM generate_series(1, 150000) AS g;
CREATE INDEX reviews_product_id_idx ON reviews (product_id);

RESET ROLE;

-- Statement statistics live in a schema only the platform owns: the app role can't drop or
-- replace them, and resetting them needs a superuser.
CREATE SCHEMA monitor;
CREATE EXTENSION pg_stat_statements SCHEMA monitor;
GRANT USAGE ON SCHEMA monitor TO shopkart;
ALTER ROLE shopkart SET search_path = "$user", public, monitor;

-- A read-only role for the verifier's checks and the Database panel (they run in the
-- platform's probe container). Its queries pin search_path and qualify catalog names, so
-- objects the app role creates can't stand in for what it reads.
CREATE ROLE verifier LOGIN PASSWORD 'verifier';
GRANT CONNECT ON DATABASE shopkart TO verifier;
GRANT USAGE ON SCHEMA public, monitor TO verifier;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO verifier;
ALTER DEFAULT PRIVILEGES FOR ROLE shopkart IN SCHEMA public GRANT SELECT ON TABLES TO verifier;
GRANT pg_read_all_stats TO verifier;

ANALYZE;
