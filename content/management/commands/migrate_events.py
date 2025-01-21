from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
from content.models import Event, EventV4, Event_Occurrence  # Importiere deine Modelle entsprechend
from django.db.models import Count  # Count importieren

class Command(BaseCommand):
    help = 'Migrate Events with future occurrences to EventV4, including the occurrence dates'

    def handle(self, *args, **kwargs):
        # Hole das aktuelle Datum und Zeit
        current_time = now()

        # Hole die Events, die zu den zukünftigen Vorkommnissen gehören
        events_to_migrate = Event.objects.filter(event_date__gt=current_time).distinct()

        # Zähle die Events, die migriert werden sollen
        total_events = events_to_migrate.count()
        if total_events == 0:
            self.stdout.write(self.style.WARNING("Keine Events mit zukünftigen Vorkommnissen gefunden."))
            return

        self.stdout.write(f"{total_events} Events gefunden, die migriert werden sollen.")

        migrated_count = 0

        # Schleife durch alle Events mit zukünftigen Vorkommnissen
        for event in events_to_migrate:
            # Erstelle ein neues EventV4 Objekt
            event_v4 = EventV4(
                title=event.title,
                content=event.content,
                date=event.event_date,  # Verwende das ursprüngliche Datum
                start_date=event.event_date,
                moddate=event.moddate,
                link=event.link,
                foreign_id=None,  # Setze foreign_id auf None, da sie nicht relevant ist
                image_url=event.image_url,
                image=event.image,
                image_source=event.image_source,
                zip_code=event.zip_code,
                street=event.street,
                town=event.town,
                event_location=event.event_location,
                published=event.published,
                reviewed=event.reviewed,
                up_for_review=event.up_for_review,
                draft=event.draft,
                source=event.source,
            )

            # Speichern des neuen EventV4 Objekts
            event_v4.save()

            # Tags (Themes) und Links (EventLinks) übernehmen
            event_v4.tags.set(event.tags.all())
            event_v4.event_links.set(event.event_links.all())
            event_v4.area.set(event.area.all())

            # Enddatum festlegen: Falls kein end_date vorhanden ist, setze es auf einen Tag nach dem event_date
            if event.event_end_date:
                end_date = event.event_end_date
            else:
                end_date = event.event_date + timedelta(days=1)

            # Vorkommnisse migrieren (start_datetime und end_datetime)
            event_v4.occurrences.create(
                start_datetime=event.event_date,
                end_datetime=end_date
            )

            # Event wurde erfolgreich migriert
            migrated_count += 1
            self.stdout.write(self.style.SUCCESS(f"Event '{event.title}' mit zukünftigen Vorkommnissen erfolgreich migriert."))

        self.stdout.write(self.style.SUCCESS(f"{migrated_count} von {total_events} Events erfolgreich migriert."))

               # Finde alle Event-Titel, die mehr als einmal in der EventV4-Datenbank vorkommen
        duplicate_events = EventV4.objects.values('title').annotate(title_count=Count('id')).filter(title_count__gt=1)

        if not duplicate_events:
            self.stdout.write(self.style.SUCCESS("Keine doppelten Events gefunden."))
            return

        self.stdout.write(f"{len(duplicate_events)} Events mit doppelten Titeln gefunden, die zusammengeführt werden sollen.")

        # Schleife durch alle doppelten Event-Titel
        for event_group in duplicate_events:
            title = event_group['title']
            
            # Hole alle Events mit demselben Titel
            events_with_same_title = EventV4.objects.filter(title=title).order_by('id')

            # Wähle das erste Event als Haupt-Event
            main_event = events_with_same_title.first()

            # Schleife durch die restlichen Events und migriere ihre Occurrences zum Haupt-Event
            all_occurrences = []
            for duplicate_event in events_with_same_title[1:]:
                # Übertrage alle Occurrences vom Duplikat zum Haupt-Event
                occurrences_to_migrate = Event_Occurrence.objects.filter(event=duplicate_event)
                
                for occurrence in occurrences_to_migrate:
                    occurrence.event = main_event  # Ändere das Event auf das Haupt-Event
                    occurrence.save()  # Speichern
                    all_occurrences.append(occurrence)  # Füge zu unserer Occurrence-Liste hinzu

                # Lösche das Duplikat-Event, nachdem alle Occurrences übertragen wurden
                duplicate_event.delete()

            # Füge die Occurrences des Haupt-Events hinzu
            all_occurrences += list(Event_Occurrence.objects.filter(event=main_event))

            # Sortiere alle Occurrences nach ihrem Startdatum
            all_occurrences.sort(key=lambda x: x.start_datetime)

            # Aktualisiere das start_date des Haupt-Events auf die erste Occurrence
            if all_occurrences:
                earliest_occurrence = all_occurrences[0]
                main_event.start_date = earliest_occurrence.start_datetime
                main_event.save()

            self.stdout.write(self.style.SUCCESS(f"Alle Occurrences von Events mit dem Titel '{title}' erfolgreich zusammengeführt und start_date aktualisiert."))

        self.stdout.write(self.style.SUCCESS("Zusammenführung und Aktualisierung der Events abgeschlossen."))