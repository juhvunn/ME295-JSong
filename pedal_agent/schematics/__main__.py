"""python -m pedal_agent.schematics <block_id> [name=value ...] --out file.png|.svg"""
import argparse

from pedal_agent.schematics import BLOCKS, check_drawing, draw, sketch


def value(v: str):
    try:
        return float(v)
    except ValueError:
        return v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pedal_agent.schematics")
    ap.add_argument("block_id", choices=BLOCKS)
    ap.add_argument("params", nargs="*", help="name=value, e.g. drive=0.8 D_clip=led C3=100n")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    params = {k: value(v) for k, v in (p.split("=", 1) for p in args.params)}
    if problems := check_drawing(sketch(args.block_id, params)):
        print("drawing does not match the netlist:", *problems, sep="\n  ")
        return 1
    print(draw(args.block_id, params).save(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
