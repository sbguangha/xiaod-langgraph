from xiaod.cli import build_parser


def test_doctor_command_exists() -> None:
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert args.func.__name__ == "_cmd_doctor"
