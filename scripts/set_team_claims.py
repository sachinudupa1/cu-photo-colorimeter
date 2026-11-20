"""CLI wrapper: python scripts/set_team_claims.py person1@example.com ..."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.team_claims import main

if __name__ == "__main__":
    main()
