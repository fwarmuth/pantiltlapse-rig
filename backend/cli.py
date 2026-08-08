import argparse
import asyncio
import os
import sys
from pathlib import Path

import dotenv
import serial_asyncio

ENV_FILE = Path(__file__).with_name(".env")


class ESPSerialCLI:
    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.running = True

        self.current_pan = 0.0
        self.current_tilt = 0.0

    async def start(self):
        print("==================================================")
        print("  CameraCommander Serial CLI  ")
        print(f"  Connecting to {self.port} at {self.baudrate} baud...")
        print("==================================================")

        try:
            self.reader, self.writer = await serial_asyncio.open_serial_connection(
                url=self.port, baudrate=self.baudrate
            )
        except Exception as e:
            print(f"\n❌ Failed to open serial port {self.port}: {e}")
            sys.exit(1)

        print("✅ Connected to serial port!")
        print("\nCommands:")
        print("  M <pan> <tilt>   : Move absolute degrees (e.g. 'M 10 0' or 'M 0 5')")
        print("  pan <delta>      : Relative Pan delta (e.g. 'pan 5' or 'pan -5')")
        print("  tilt <delta>     : Relative Tilt delta (e.g. 'tilt 5' or 'tilt -5')")
        print("  S                : Query status (pan, tilt, driver state)")
        print("  V                : Query firmware version")
        print("  d / e            : Disable / Enable motor drivers")
        print("  X                : Emergency stop")
        print("  q / exit         : Quit CLI\n")

        # Start background reader task
        asyncio.create_task(self._listen_serial())

        # Query initial status
        await self._send("V")
        await self._send("S")
        await asyncio.sleep(0.2)

        # Loop for user stdin input
        loop = asyncio.get_running_loop()
        while self.running:
            try:
                line = await loop.run_in_executor(None, input, "cameracommander > ")
                line = line.strip()
                if not line:
                    continue
                if line.lower() in ("q", "quit", "exit"):
                    print("Exiting CLI...")
                    self.running = False
                    break

                await self._handle_user_input(line)
            except (KeyboardInterrupt, EOFError):
                print("\nExiting CLI...")
                self.running = False
                break

    async def _send(self, cmd: str):
        if self.writer:
            print(f"  > [TX]: {cmd}")
            self.writer.write(f"{cmd}\n".encode("ascii"))
            await self.writer.drain()

    async def _handle_user_input(self, text: str):
        parts = text.split()
        cmd = parts[0].lower()

        if cmd == "pan" and len(parts) >= 2:
            try:
                delta = float(parts[1])
                target_pan = self.current_pan + delta
                # Immediately update local target tracker
                self.current_pan = target_pan
                await self._send(f"M {target_pan:.2f} {self.current_tilt:.2f}")
                # Query hardware for status confirmation
                await asyncio.sleep(0.1)
                await self._send("S")
            except ValueError:
                print("❌ Usage: pan <delta_deg> (e.g. 'pan 5')")
        elif cmd == "tilt" and len(parts) >= 2:
            try:
                delta = float(parts[1])
                target_tilt = self.current_tilt + delta
                # Immediately update local target tracker
                self.current_tilt = target_tilt
                await self._send(f"M {self.current_pan:.2f} {target_tilt:.2f}")
                # Query hardware for status confirmation
                await asyncio.sleep(0.1)
                await self._send("S")
            except ValueError:
                print("❌ Usage: tilt <delta_deg> (e.g. 'tilt 5')")
        elif cmd == "m" and len(parts) >= 3:
            try:
                self.current_pan = float(parts[1])
                self.current_tilt = float(parts[2])
                await self._send(text)
                await asyncio.sleep(0.1)
                await self._send("S")
            except ValueError:
                await self._send(text)
        else:
            # Send verbatim text to serial port
            await self._send(text)

    async def _listen_serial(self):
        while self.running and self.reader:
            try:
                line_bytes = await self.reader.readline()
                if line_bytes:
                    line = line_bytes.decode("ascii", errors="replace").strip()
                    print(f"\n  < [RX]: {line}")
                    self._update_telemetry(line)
                    # Re-print prompt if waiting for input
                    sys.stdout.write("cameracommander > ")
                    sys.stdout.flush()
            except Exception as e:
                if self.running:
                    print(f"\n❌ Serial read error: {e}")
                await asyncio.sleep(0.5)

    def _update_telemetry(self, line: str):
        if line.startswith("STATUS"):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    self.current_pan = float(parts[1])
                    self.current_tilt = float(parts[2])
                except ValueError:
                    pass


def create_argument_parser() -> argparse.ArgumentParser:
    dotenv.load_dotenv(dotenv_path=ENV_FILE)

    parser = argparse.ArgumentParser(
        description="CameraCommander Serial CLI Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", default=os.getenv("SERIAL_PORT", "/dev/ttyUSB0"), help="Serial port")

    baud_value = os.getenv("SERIAL_BAUD", "9600")
    try:
        baud_default = int(baud_value)
    except ValueError:
        parser.error(f"SERIAL_BAUD must be an integer, got {baud_value!r}")

    parser.add_argument("--baud", type=int, default=baud_default, help="Baud rate")
    return parser


def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    cli = ESPSerialCLI(port=args.port, baudrate=args.baud)
    try:
        asyncio.run(cli.start())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
