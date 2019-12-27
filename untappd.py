#!/usr/bin/env python3
import json, csv, argparse, os

p = argparse.ArgumentParser()
p.add_argument('--beer', action='store_true', help='remove duplicate beers')
p.add_argument('--venue', action='store_true', help='remove duplicate venues')
p.add_argument('file', help='name of the json file to extract uniques from')
a = p.parse_args()

data = json.load(open(a.file))
fn = os.path.splitext(a.file)[0]
fne = f'{fn}-uniques.csv'
fnej = f'{fn}-uniques.json'

if a.venue == True:
    key = 'venue_name' # No venue urls, have to sort by name with consequences.
if a.beer == True:
    key = 'beer_url' # Sort by url because some breweries name beers the same thing

uniques = list({x[key]: x for x in data}.values())
csv_header = list(data[0].keys())  # Get headers from file
dupes = len(data) - len(uniques)

print(f'You have {len(data)} total check-ins with {len(uniques)} uniques '
      f'and {dupes} duplicates\n')

with open(fne, 'w') as fcsv:
    cw = csv.DictWriter(fcsv, fieldnames=csv_header)
    cw.writeheader()
    for i in range(0, len(uniques)):
        cw.writerow(uniques[i])

with open(fnej, 'w') as fjson:
    json.dump(uniques, fjson, separators=(',', ':'))

print(f'Created {fne} and {fnej} with just your unique beer'
      ' check-ins')

