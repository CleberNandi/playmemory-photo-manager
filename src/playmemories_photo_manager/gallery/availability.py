"""Read-only visibility policy for confirmed absence, distinct from an offline root."""

# Correlates against the Asset alias `a`. No locations is not evidence of absence.
# Any surviving occurrence or offline root keeps the Asset visible.
EXCLUDE_MISSING_SQL = """(? = 0
    OR NOT EXISTS (SELECT 1 FROM file_location fl WHERE fl.asset_id = a.id)
    OR EXISTS (
        SELECT 1 FROM file_location fl JOIN library_root lr ON lr.id = fl.library_root_id
        WHERE fl.asset_id = a.id
          AND (fl.availability <> 'missing' OR lr.availability = 'offline')
    ))"""
