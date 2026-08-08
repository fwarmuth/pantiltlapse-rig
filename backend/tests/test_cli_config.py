import cli


def test_cli_uses_environment_defaults(monkeypatch):
    monkeypatch.setenv("SERIAL_PORT", "/dev/test-serial")
    monkeypatch.setenv("SERIAL_BAUD", "115200")

    args = cli.create_argument_parser().parse_args([])

    assert args.port == "/dev/test-serial"
    assert args.baud == 115200


def test_cli_arguments_override_environment(monkeypatch):
    monkeypatch.setenv("SERIAL_PORT", "/dev/from-env")
    monkeypatch.setenv("SERIAL_BAUD", "9600")

    args = cli.create_argument_parser().parse_args(["--port", "/dev/from-cli", "--baud", "57600"])

    assert args.port == "/dev/from-cli"
    assert args.baud == 57600
