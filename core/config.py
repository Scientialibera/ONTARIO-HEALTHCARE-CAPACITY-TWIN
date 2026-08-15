from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "processed"
FRONTEND_DIR = BASE_DIR / "frontend"

DEFAULT_ED_VISITS_PER_CAPITA = 0.39
SENTINEL_NETWORK_CAPTURE_SHARE = 0.30
DEFAULT_ACCESS_TARGET_MINUTES = 30
E2SFCA_CATCHMENT_MINUTES = 120

# Distance-decay weights adapted from the E2SFCA literature. They are planning
# parameters rather than Ontario policy thresholds.
DECAY_BANDS = (
    (15.0, 1.00),
    (30.0, 0.68),
    (60.0, 0.22),
    (120.0, 0.05),
)
