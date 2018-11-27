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

def dupeFinder():
    print('Reading ' + a.file + ' and detecting duplicate beers')
    btlist = []

    for i in range(0, len(data)):
        beertupl = data[i]['beer_name'], data[i]['beer_url']  # different breweries name beers the same name
        btlist.append(beertupl)

    uniques = []
    dupes = []
    uniqueindexes = []
    for i in range(0, len(btlist)):
        if btlist[i] not in uniques:
            uniques.append(btlist[i])
            uniqueindexes.append(i)
        else:
            dupes.append(btlist[i])
    print("You have " + str(len(btlist)) + ' total check-ins with ' + str(len(uniques)) + ' uniques and ' +
          str(len(dupes)) + ' duplicates')
    return uniqueindexes


def createcsv(indexes):
    with open(fne, 'w') as f:
        cw = csv.writer(f)
        cw.writerow(['beer_name', 'brewery_name', 'beer_type', 'beer_abv', 'beer_ibu', 'comment', 'venue_name',
                     'venue_city', 'venue_state', 'venue_country', 'venue_lat', 'venue_lng', 'rating_score',
                     'created_at', 'checkin_url', 'beer_url', 'brewery_url', 'brewery_country', 'brewery_city',
                     'brewery_state', 'flavor_profiles', 'purchase_venue', 'serving_type'])
        for i in indexes:
            cw.writerow([data[i]['beer_name'], data[i]['brewery_name'], data[i]['beer_type'], data[i]['beer_abv'],
                        data[i]['beer_ibu'], data[i]['comment'], data[i]['venue_name'], data[i]['venue_city'],
                        data[i]['venue_state'], data[i]['venue_country'], data[i]['venue_lat'],
                        data[i]['venue_lng'], data[i]['rating_score'], data[i]['created_at'],
                        data[i]['checkin_url'], data[i]['beer_url'], data[i]['brewery_url'],
                        data[i]['brewery_country'], data[i]['brewery_city'], data[i]['brewery_state'],
                        data[i]['flavor_profiles'], data[i]['purchase_venue'], data[i]['serving_type']])


def createjson():
    ucsv = open(fne, 'r')
    ujson = open(fnej, 'w')
    r = csv.DictReader(ucsv)
    ujson.write('[')
    for i in r:
        json.dump(i, ujson)
        ujson.write(',')
    ujson.write(']')


def main():
    print('\n')
    indexes = dupeFinder()
    createcsv(indexes)
    createjson()
    print('Created ' + fne + ' and ' + fnej + ' with just your unique beer check-ins')

main()
