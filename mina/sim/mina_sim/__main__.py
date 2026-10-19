import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from mina_sim.app import main


def cli() -> None:
    parser = argparse.ArgumentParser(description="Simulador da Mina no computador")
    parser.add_argument("--web", type=int, default=8765, help="porta da página")
    parser.add_argument("--ws", type=int, default=8766, help="porta do WebSocket local")
    parser.add_argument(
        "--backend",
        default="ws://127.0.0.1:8000/v1/audio",
        help="WebSocket do backend da Mina",
    )
    args = parser.parse_args()
    asyncio.run(main(web_port=args.web, ws_port=args.ws, backend_url=args.backend))


if __name__ == "__main__":
    cli()
