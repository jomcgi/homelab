-- knowledge.gaps: widen state CHECK to admit research-pipeline values.
--
-- Original CHECK (20260424000000) allowed: discovered, classified, in_review,
-- researched, verified, consolidated, committed, rejected.
-- The external research pipeline introduces 'researching' (worker holding
-- the lock) and 'parked' (3 consecutive Sonnet rejections). Both must be
-- accepted at the DB layer for the handler's UPDATE statements to succeed
-- on Postgres. SQLite silently ignores CHECK constraints, so this gap was
-- not caught in the test suite.
ALTER TABLE knowledge.gaps DROP CONSTRAINT IF EXISTS gaps_state_check;
ALTER TABLE knowledge.gaps ADD CONSTRAINT gaps_state_check CHECK (
  state IN (
    'discovered', 'classified', 'in_review',
    'researching', 'researched',
    'verified', 'consolidated',
    'committed', 'parked', 'rejected'
  )
);
