"""Print the workspace address and key. Used by the launchers: python -m app.launch_info [port]."""
import sys

from . import __version__
from .product import SECRET


def main(port: str = "8765") -> None:
    print(f"\n  SIYAJ assurance workspace {__version__}")
    print(f"  Open   http://127.0.0.1:{port}")
    print(f"  Key    {SECRET}")
    print("  The key is also saved in data/admin_token.txt. Keep it private.")
    print("  Leave this window open while you use SIYAJ. Press Ctrl+C to stop it.\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "8765")
