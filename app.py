import os
import socket
import webbrowser
from threading import Timer

from server import app


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print(f"이 노트북: http://localhost:{port}")
    print(f"같은 Wi-Fi의 다른 기기: http://{local_ip()}:{port}")
    Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(host="0.0.0.0", port=port, debug=False)
