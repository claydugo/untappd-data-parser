# untappd-data-cleaner
[![License](https://img.shields.io/github/license/mashape/apistatus.svg)](https://github.com/claydugo/untappd-data-cleaner/blob/master/LICENSE)

## Info
[Untappd](https://untappd.com/) allows you to download your checkin data in JSON and CSV formats. This is great, however they do not have an option to download the data of just your 'unique' checkins. Personally I have checked in my favorite beer over 50 times with a rating of 5 stars and this skews the overall average ratings of the beer I have drank. This script will take the json file you downloaded from untappd and create a json and a csv file with only your first checkins of each beer.

## Usage

Run `python3 untappd.py <UNTAPPD-DATA>.json`

or

`./untappd.py <UNTAPPD-DATA>.json`

![output](https://github.com/claydugo/untappd-data-cleaner/blob/master/scr/untappd-uniques-cl.png?raw=true)

## License
MIT
