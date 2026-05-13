import os
import socket
import sys


def main() -> int:
    print("-> Checking Python runtime dependencies...")
    try:
        import fastapi  # noqa: F401
        import pydantic  # noqa: F401
        import uvicorn  # noqa: F401
        print("   [OK] Dependencies are available")
    except ImportError as exc:
        print(f"   [ERROR] Missing dependency: {exc.name}")
        return 1

    print("-> Checking API port 8080...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(("127.0.0.1", 8080)) == 0:
            print("   [ERROR] Port 8080 is already in use")
            return 1
    print("   [OK] Port 8080 is available")

    print("-> Checking tools directory...")
    if not os.path.exists("tools"):
        os.makedirs("tools")
        print("   [INFO] Created ./tools directory")
    else:
        print("   [OK] Tools directory exists")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
