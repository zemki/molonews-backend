#!/bin/bash

set -e
source /home/molonews/molonews/venv/bin/activate
python /home/molonews/molonews/manage.py import_articles
