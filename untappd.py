#!/usr/bin/env python3
import json
import csv
import argparse
import os
from datetime import datetime

# This is obviously subjective
# I'm most concerned with not showcasing
# how the sausage is made
# So I just specify the few that I actually want
good_keys = [
    'beer_name',
	'brewery_name',
	'beer_type',
	'venue_name',
	'venue_lat',
	'venue_lng',
	'created_at',
]


def parse_beer_data(beer_data, key):
    return list({x[key]: x for x in beer_data}.values())

def purge_backend_keys(beer_json, backend_keys):
    return [dict((k,v) for k,v in check_in.items() if k not in backend_keys) for check_in in beer_json]

def string_parse_keys(beer_json):
    return [dict((k.replace('_', ' ').title(), v) for k,v in check_in.items()) for check_in in beer_json]

def fancy_date_format(beer_json):
    for check_in in beer_json:
        date = check_in.pop('created_at', None)
        if date is not None:
            date = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y at %I:%M%p')
        check_in['Date Drank'] =  date
    return beer_json

def make_untappd_files(filename, beer_data):
    csv_header = list(beer_data[-1].keys())  # Get headers from file
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
    p.add_argument('--no_human_keys', action=argparse.BooleanOptionalAction)
    p.add_argument('--no_strip_backend', action=argparse.BooleanOptionalAction)
    p.add_argument('--no_fancy_date_format', action=argparse.BooleanOptionalAction)
    p.add_argument('file', help='name of the json file to extract unique_beers from')
    arguments = p.parse_args()

    if arguments.key:
        key = arguments.key
    else:
        key = 'bid' # If no key specified sort by unique beers

    beer_data = json.load(open(arguments.file))
    file_name = os.path.splitext(arguments.file)[0] + f'_unique_{key}'

    unique_beers = parse_beer_data(beer_data, key)

    if not arguments.no_strip_backend:
        backend_keys = [key for key in beer_data[-1].keys() if key not in good_keys]
        unique_beers = purge_backend_keys(unique_beers, backend_keys)

    if not arguments.no_fancy_date_format:
        unique_beers = fancy_date_format(unique_beers)

    if not arguments.no_human_keys:
        unique_beers = string_parse_keys(unique_beers)

    make_untappd_files(file_name, unique_beers)
    duplicate_beers = len(beer_data) - len(unique_beers)

    print(f'You have {len(beer_data)} total check-ins with {len(unique_beers)} unique {key}\'s '
          f'and {duplicate_beers} duplicates\n')

