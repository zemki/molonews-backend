from django.core.management.base import BaseCommand
from content.models import EventV4, Event_Occurrence  # Importiere deine Modelle entsprechend
from django.db.models import Count

class Command(BaseCommand):
    help = 'Consolidate and merge overlapping Event_Occurrences for each EventV4'

    def handle(self, *args, **kwargs):
        # Finde alle Events in EventV4
        events = EventV4.objects.all()

        if not events:
            self.stdout.write(self.style.SUCCESS("Keine Events gefunden."))
            return

        self.stdout.write(f"{len(events)} Events gefunden, die überprüft und deren Occurrences zusammengeführt werden sollen.")

        for event in events:
            # Finde alle Occurrences für das aktuelle Event und sortiere sie nach start_datetime
            occurrences = list(Event_Occurrence.objects.filter(event=event).order_by('start_datetime'))

            if not occurrences:
                continue

            # Liste zur Speicherung der zusammengeführten Occurrences
            merged_occurrences = []
            current_start = occurrences[0].start_datetime
            current_end = occurrences[0].end_datetime

            for occurrence in occurrences[1:]:
                # Wenn die Occurrence überlappt oder direkt an die aktuelle grenzt, erweitere den Zeitraum
                if occurrence.start_datetime <= current_end:
                    # Aktualisiere das Enddatum, falls dieses Occurrence einen späteren Endzeitpunkt hat
                    current_end = max(current_end, occurrence.end_datetime)
                else:
                    # Speichere den aktuellen kombinierten Zeitraum
                    merged_occurrences.append((current_start, current_end))
                    # Setze den neuen aktuellen Zeitraum
                    current_start = occurrence.start_datetime
                    current_end = occurrence.end_datetime

            # Speichere das letzte kombinierte Occurrence
            merged_occurrences.append((current_start, current_end))

            # Lösche alle alten Occurrences für dieses Event
            Event_Occurrence.objects.filter(event=event).delete()

            # Erstelle neue Occurrences basierend auf den zusammengeführten Zeiträumen
            for start, end in merged_occurrences:
                Event_Occurrence.objects.create(event=event, start_datetime=start, end_datetime=end)

            self.stdout.write(self.style.SUCCESS(f"Occurrences für Event '{event.title}' erfolgreich zusammengeführt."))

        self.stdout.write(self.style.SUCCESS("Zusammenführung aller Event_Occurrences abgeschlossen."))
