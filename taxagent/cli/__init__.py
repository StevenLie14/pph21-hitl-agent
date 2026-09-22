from __future__ import annotations

import argparse
import logging

from ..settings import get_settings
from ..taxes import get as tax_module
from . import agent, drafting, monitor
from ._common import show_result

__all__ = ["build_parser", "main", "show_result"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pph21", description="Agent penghitung PPh Pasal 21")
    sub = p.add_subparsers(dest="command", required=True)
    tax = tax_module()
    if tax.register_cli is not None:
        tax.register_cli(sub)
    for module in (agent, monitor, drafting):
        module.register(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=get_settings().log_level, format="%(levelname)s %(name)s: %(message)s")
    return args.handler(args)
