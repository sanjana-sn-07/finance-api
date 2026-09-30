-- Add per-user transaction ownership.
-- Run this migration against PostgreSQL BEFORE deploying the application code
-- that makes transactions.user_id NOT NULL at the ORM level.
--
-- Legacy rows can only be backfilled automatically when exactly one user exists.
-- If multiple users exist and orphaned legacy transactions are present, the
-- migration aborts instead of assigning financial data to the wrong account.

BEGIN;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS user_id INTEGER;

DO $$
DECLARE
    orphan_count INTEGER;
    app_user_count INTEGER;
    legacy_user_id INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphan_count
    FROM transactions
    WHERE user_id IS NULL;

    IF orphan_count > 0 THEN
        SELECT COUNT(*) INTO app_user_count FROM users;

        IF app_user_count = 1 THEN
            SELECT id INTO legacy_user_id FROM users LIMIT 1;
            UPDATE transactions
            SET user_id = legacy_user_id
            WHERE user_id IS NULL;
        ELSE
            RAISE EXCEPTION
                'Cannot safely backfill % legacy transactions: expected exactly 1 user, found %. Assign transactions.user_id explicitly, then rerun this migration.',
                orphan_count,
                app_user_count;
        END IF;
    END IF;
END
$$;

ALTER TABLE transactions
    ALTER COLUMN user_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_transactions_user_id'
    ) THEN
        ALTER TABLE transactions
            ADD CONSTRAINT fk_transactions_user_id
            FOREIGN KEY (user_id)
            REFERENCES users(id)
            ON DELETE CASCADE;
    END IF;
END
$$;

-- Remove the old global uniqueness rule. Depending on how SQLAlchemy created
-- the original schema, it may exist as a constraint or a unique index.
ALTER TABLE transactions
    DROP CONSTRAINT IF EXISTS transactions_plaid_transaction_id_key;
DROP INDEX IF EXISTS ix_transactions_plaid_transaction_id;

CREATE INDEX IF NOT EXISTS ix_transactions_user_id
    ON transactions(user_id);
CREATE INDEX IF NOT EXISTS ix_transactions_plaid_transaction_id
    ON transactions(plaid_transaction_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_transactions_user_plaid_transaction'
    ) THEN
        ALTER TABLE transactions
            ADD CONSTRAINT uq_transactions_user_plaid_transaction
            UNIQUE (user_id, plaid_transaction_id);
    END IF;
END
$$;

COMMIT;
