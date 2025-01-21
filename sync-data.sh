#!/usr/bin/env bash

set -e

remote_dbname=django
local_dbname=django

info() {
	python -c "print ((' $1 ').center(80, '*'))"
}

info "checking if connecting to molo works"
ssh molo "echo works."
echo

info "checking if ./manage.py works"
./manage.py > /dev/null
echo 'works.'
echo

info "dumping db on server"
ssh molo "pg_dump ${remote_dbname} | gzip -9 > /tmp/db.dump.gz"
echo 'done.'
echo

info "downloading dump"
scp molo:/tmp/db.dump.gz /tmp/db.dump.gz
echo

info "removing dump on server"
ssh molo "rm /tmp/db.dump.gz"
echo

info "unpacking dump"
gunzip /tmp/db.dump.gz
echo

if psql -lqt | cut -d \| -f 1 | grep '\sdjango\s'; then
        info "removing local db"
        dropdb ${local_dbname}
        echo
fi

info "creating local db"
createdb django
echo

info "restoring dump"
psql django < /tmp/db.dump
echo

info "removing local dump"
rm /tmp/db.dump
echo

info "running migrations"
./manage.py migrate
echo

info "settings passwords for all users to \"ok\""
./manage.py set_fake_passwords --password=ok
echo

#info "syncing media/"
#rsync -avyL molo:/home/mappa/sites/editor/backend/media/ media
#echo
