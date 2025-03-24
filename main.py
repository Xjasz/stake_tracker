import argparse
from stake_shared import run_stake_game

def main():
    parser = argparse.ArgumentParser(description="Run Stake Tracker Modules")
    parser.add_argument(
        "--mode",
        choices=["crash", "slide", "both"],
        required=True,
        help="Select which module(s) to run"
    )
    args = parser.parse_args()
    if args.mode in ("crash", "both"):
        run_stake_game("crash")
    if args.mode in ("slide", "both"):
        run_stake_game("slide")

if __name__ == "__main__":
    main()