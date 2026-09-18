from datetime import timedelta


# One heartbeat policy governs both API admission checks and project-load recovery.
CHAPTER_STALE_TIMEOUT = timedelta(minutes=10)
