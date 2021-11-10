#!/usr/bin/env python3
import json, csv, argparse, os


def parseData(data, key):
    uniques = list({x[key]: x for x in data}.values())
    dupes = len(data) - len(uniques)

    print(f'You have {len(data)} total check-ins with {len(uniques)} unique {key}\'s '
          f'and {dupes} duplicates\n')

    return uniques

def makeFiles(filename, data):
    csv_header = list(data[0].keys())  # Get headers from file
    with open(f'{filename}-uniques.csv', 'w') as fcsv:
        cw = csv.DictWriter(fcsv, fieldnames=csv_header)
        cw.writeheader()
        for i in range(0, len(data)):
            cw.writerow(data[i])

    with open(f'{fn}-uniques.json', 'w') as fjson:
        json.dump(data, fjson, separators=(',', ':'))

    print('Created JSON and CSV with just your unique beer'
      ' check-ins')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--key', choices=['brewery_name', 'venue_name', 'beer_type', 'photo_url'])
    p.add_argument('file', help='name of the json file to extract uniques from')
    a = p.parse_args()

    if a.key:
        key = a.key
    else:
        key = 'bid' # If no key specified sort by unique beers

    data = json.load(open(a.file))
    fn = os.path.splitext(a.file)[0]

    makeFiles(fn, parseData(data, key))

