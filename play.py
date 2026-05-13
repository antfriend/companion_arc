import os
import sys
import arc_agi
from arc_agi import OperationMode
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("ARC_API_KEY"):
    print("ARC_API_KEY not set. Add it to .env or set it in your environment.")
    sys.exit(1)


def pick_action(actions: list) -> object | None:
    print("\nAvailable actions:")
    for i, action in enumerate(actions):
        print(f"  {i}: {action}")
    raw = input("\nAction (number or 'quit'): ").strip().lower()
    if raw == "quit":
        return None
    try:
        return actions[int(raw)]
    except (ValueError, IndexError):
        print("Invalid — try again.")
        return pick_action(actions)


def main():
    game_id = input("Game ID (e.g. ls20): ").strip()

    arc = arc_agi.Arcade(operation_mode=OperationMode.COMPETITION)
    env = arc.make(game_id)

    print(f"\nStarted '{game_id}' in COMPETITION mode.")
    print("Consult @LOCUS in Claude Code before committing each action.\n")

    while True:
        actions = env.action_space
        if not actions:
            print("\nNo actions available — level complete.")
            break

        action = pick_action(actions)
        if action is None:
            print("\nSession ended by user.")
            break

        obs = env.step(action)
        print(f"\nstate={obs.state}  levels_completed={obs.levels_completed}  win_levels={obs.win_levels}")
        if obs.frame:
            for i, grid in enumerate(obs.frame):
                print(f"frame[{i}]:\n{grid}")

        if hasattr(obs, "state") and obs.state in ("win", "game_over"):
            print(f"\nLevel ended: {obs.state}")
            break

    print("\n--- Scorecard ---")
    print(arc.get_scorecard())


if __name__ == "__main__":
    main()
