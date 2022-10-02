#!/usr/bin/env python3
import json, csv, argparse, os


def parse_beer_data(beer_data, key):
    unique_beers = list({x[key]: x for x in beer_data}.values())
    duplicate_beers = len(beer_data) - len(unique_beers)

    print(f'You have {len(beer_data)} total check-ins with {len(unique_beers)} unique {key}\'s '
          f'and {duplicate_beers} duplicates\n')

    return unique_beers

def make_untappd_files(filename, beer_data):
    csv_header = list(beer_data[0].keys())  # Get headers from file
    with open(f'{filename}.csv', 'w') as fcsv:
        csv_writer = csv.DictWriter(fcsv, fieldnames=csv_header)
        csv_writer.writeheader()
        for check_in in range(0, len(beer_data)):
            csv_writer.writerow(beer_data[check_in])

    with open(f'{filename}.json', 'w') as fjson:
        json.dump(beer_data, fjson, separators=(',', ':'))

    print('Created JSON and CSV with just your unique'
      ' check-ins')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--key', choices=['brewery_name', 'venue_name', 'beer_type', 'photo_url'])
    p.add_argument('file', help='name of the json file to extract unique_beers from')
    arguments = p.parse_args()

    if arguments.key:
        key = arguments.key
    else:
        key = 'bid' # If no key specified sort by unique beers

    beer_data = json.load(open(arguments.file))
    file_name = os.path.splitext(arguments.file)[0] + f'_unique_{key}'

    make_untappd_files(file_name, parse_beer_data(beer_data, key))

