-- knowledge.gaps: track research attempt count for the external research
-- pipeline. After 3 consecutive Sonnet rejections, the research worker
-- parks the gap (state='parked'). See
-- docs/plans/2026-04-25-external-research-pipeline-design.md.
ALTER TABLE knowledge.gaps
  ADD COLUMN research_attempts INTEGER NOT NULL DEFAULT 0;
