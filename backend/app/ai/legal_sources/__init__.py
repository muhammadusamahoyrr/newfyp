"""Legal-source provenance: who issued a text, what kind of authority it is,
and whether it is known to be in force on a date (2026-10-16).

Pure code. Nothing here opens Chroma, MongoDB or the network, so it can be
imported by tests, pilots and build scripts without touching a live store.

  identity  -- parse the NUMBERS that identify an instrument or a provision:
               Act/Ordinance numbers, S.R.O. numbers, regulator circulars, and
               a provision reference (section vs CPC Order/Rule vs Article vs a
               schedule entry vs a court practice rule), which are easy to
               confuse and have been confused in this corpus before.
  registry  -- the source record, its retrieval lane and authority class, its
               validation, and its temporal status on a date. A record is never
               "in force" unless its commencement was verified.
"""
