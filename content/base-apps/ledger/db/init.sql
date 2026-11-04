-- Ledger schema and seed: 1,000 customer wallets, 20 merchants and the house account, in
-- double-entry books. Runs once when the Postgres image is built.
--
-- Double entry: every transfer writes two entries that sum to zero, and an account's balance
-- is the sum of its entries. The house account funded every opening balance, so it is the
-- only one below zero, and all balances together always add up to exactly zero.
--
-- Roles (ADR 015). `postgres` is the platform's superuser, reached only through the
-- container's local socket. The app and the player use `ledger`, which owns the tables but is
-- not a superuser. The verifier reads as `verifier`.

CREATE ROLE ledger LOGIN PASSWORD 'ledger';
GRANT USAGE, CREATE ON SCHEMA public TO ledger;
GRANT pg_read_all_stats TO ledger;
REVOKE TEMPORARY ON DATABASE ledger FROM PUBLIC;
GRANT TEMPORARY ON DATABASE ledger TO ledger;

SET ROLE ledger;

CREATE TABLE accounts (
    id            integer PRIMARY KEY,
    owner         text NOT NULL,
    kind          text NOT NULL CHECK (kind IN ('house', 'customer', 'merchant')),
    balance_cents bigint NOT NULL,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- No foreign keys from the books to accounts: inserting an entry would take a key-share lock
-- on its account row, and every payment row-locks the house account, so bookkeeping and
-- payments would queue behind each other. The API checks the accounts exist.
CREATE TABLE transfers (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_account    integer NOT NULL,
    to_account      integer NOT NULL,
    amount_cents    bigint NOT NULL CHECK (amount_cents > 0),
    kind            text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE entries (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transfer_id   bigint NOT NULL REFERENCES transfers(id),
    account_id    integer NOT NULL,
    amount_cents  bigint NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX entries_account_id_idx ON entries (account_id);
CREATE INDEX entries_transfer_id_idx ON entries (transfer_id);

-- Card captures from the card network, waiting to be paid out to merchants by the worker.
CREATE TABLE settlements (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    merchant_id   integer NOT NULL,
    amount_cents  bigint NOT NULL CHECK (amount_cents > 0),
    status        text NOT NULL DEFAULT 'pending',
    transfer_id   bigint REFERENCES transfers(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    settled_at    timestamptz
);
CREATE INDEX settlements_pending_idx ON settlements (id) WHERE status = 'pending';

INSERT INTO accounts (id, owner, kind, balance_cents) VALUES (0, 'Ledger Ltd (house)', 'house', 0);
INSERT INTO accounts (id, owner, kind, balance_cents)
SELECT g, 'customer-' || g, 'customer', 0 FROM generate_series(1, 1000) AS g;
INSERT INTO accounts (id, owner, kind, balance_cents)
SELECT 9000 + g, 'merchant-' || g, 'merchant', 0 FROM generate_series(1, 20) AS g;

-- Opening balances: the house funds every customer (EUR 500 to EUR 1,500) and merchant.
INSERT INTO transfers (from_account, to_account, amount_cents, kind, created_at)
SELECT 0, id, CASE WHEN kind = 'customer' THEN 50000 + (id * 7919) % 100000 ELSE 1000000 END,
       'opening', now() - interval '30 days'
FROM accounts WHERE id <> 0 ORDER BY id;
INSERT INTO entries (transfer_id, account_id, amount_cents, created_at)
SELECT id, to_account, amount_cents, created_at FROM transfers
UNION ALL
SELECT id, from_account, -amount_cents, created_at FROM transfers;
UPDATE accounts a SET balance_cents = e.total
FROM (SELECT account_id, sum(amount_cents) AS total FROM entries GROUP BY account_id) e
WHERE e.account_id = a.id;

RESET ROLE;

CREATE SCHEMA monitor;
CREATE EXTENSION pg_stat_statements SCHEMA monitor;
GRANT USAGE ON SCHEMA monitor TO ledger;
ALTER ROLE ledger SET search_path = "$user", public, monitor;

CREATE ROLE verifier LOGIN PASSWORD 'verifier';
GRANT CONNECT ON DATABASE ledger TO verifier;
GRANT USAGE ON SCHEMA public, monitor TO verifier;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO verifier;
ALTER DEFAULT PRIVILEGES FOR ROLE ledger IN SCHEMA public GRANT SELECT ON TABLES TO verifier;
GRANT pg_read_all_stats TO verifier;

ANALYZE;
