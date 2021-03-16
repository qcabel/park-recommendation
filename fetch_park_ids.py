#!/usr/bin/env

from argparse import ArgumentParser
import get_id
import pickle


def parse_args():
    parser = ArgumentParser(description="Getting Google places using Places API")
    parser.add_argument("--api-key", required=True, help="Google Places API Key")
    parser.add_argument("--type", default=[], action="append", dest="types")
    parser.add_argument('-P', "--point", help="Coordinates in lat,lng format, e.g. 55.33,-135.66",
                        default=[], action="append", dest="bounds")
    parser.add_argument("--radius", type=int, default=180,
                        help="The radius for the circle for nearby search")
    parser.add_argument("--output", required=True, help="The output file for this run.")

    args = parser.parse_args()
    return args


def parse_coords(coord):
    coords = [float(x) for x in coord.split(',')]
    assert len(coords) == 2, "You can only provide two numbers for lat,lng"

    return coords


def main():
    args = parse_args()

    assert len(args.bounds) == 2, "You must provide two points (coordinates)!"

    places = get_id.get(
        args.api_key, args.types,
        parse_coords(args.bounds[0]), parse_coords(args.bounds[1]),
        radius=args.radius
    )

    with open(args.output, 'wb+') as f:
        pickle.dump(places, f)


if __name__ == "__main__":
    main()