#!/usr/bin/env python3
import json
import csv
import argparse

p = argparse.ArgumentParser()
p.add_argument('file', help='name of the json file to extract uniques from')
a = p.parse_args()

data = json.load(open(a.file))
fne = str(a.file[:len(a.file)-5]) + '-uniques.csv'
fnej = str(a.file[:len(a.file)-5]) + '-uniques.json'
csv_header = [
    'beer_name',
    'brewery_name',
    'beer_type',
    'beer_abv',
    'beer_ibu',
    'comment',
    'venue_name',
    'venue_city',
    'venue_state',
    'venue_country',
    'venue_lat',
    'venue_lng',
    'rating_score',
    'created_at',
    'checkin_url',
    'beer_url',
    'brewery_url',
    'brewery_country',
    'brewery_city',
    'brewery_state',
    'flavor_profiles',
    'purchase_venue',
    'serving_type',
    ]


def main():
    uniques = list({x['beer_url']: x for x in data}.values())
    dupes = len(data) - len(uniques)

    print("You have " + str(len(data)) + ' total check-ins with ' +
          str(len(uniques)) + ' uniques and ' + str(dupes) + ' duplicates')

    with open(fne, 'w') as fcsv:
        cw = csv.DictWriter(fcsv, fieldnames=csv_header)
        for i in range(0, len(uniques)):
            cw.writerow(uniques[i])

    with open(fnej, 'w') as fjson:
        json.dump(uniques, fjson)

    print('\nCreated ' + fne + ' and ' + fnej +
          ' with just your unique beer check-ins')

main()
