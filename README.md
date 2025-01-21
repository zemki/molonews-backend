# Molo.news Backend

Willkommen im offiziellen Repository des Molo.news-Backends! Dieses Projekt stellt die serverseitige Infrastruktur für die Molo.news-App bereit, eine Plattform für lokale Nachrichten und Veranstaltungen.

## ✨ Projektbeschreibung
Molo.news ist eine gemeinwohlorientierte, werbefreie Nachrichten-App, die es lokalen Akteuren ermöglicht, schnell und unkompliziert relevante Informationen zu verbreiten. Die App aggregiert und kuratiert Inhalte aus verschiedenen lokalen Quellen und stellt sie den Nutzer*innen personalisiert zur Verfügung. Das Backend dieses Projekts übernimmt die Verarbeitung und Verwaltung der Inhalte sowie die Bereitstellung der API für die mobile Anwendung.

## 🛠 Installation & Einrichtung
### Voraussetzungen
- Python 3.9+
- PostgreSQL (oder eine kompatible Datenbank)
- Redis (für Caching und Warteschlangen)
- Docker (optional, für Containerisierung)

### Setup-Anleitung
1. **Repository klonen:**
   ```sh
   git clone https://github.com/dein-account/molo-news-backend.git
   cd molo-news-backend
   ```
2. **Virtuelle Umgebung erstellen und aktivieren:**
   ```sh
   python -m venv venv
   source venv/bin/activate  # macOS/Linux
   venv\Scripts\activate     # Windows
   ```
3. **Abhängigkeiten installieren:**
   ```sh
   pip install -r requirements.txt
   ```
4. **Datenbank einrichten:**
   ```sh
   createdb molo_news
   python manage.py migrate
   ```
5. **Entwicklungsserver starten:**
   ```sh
   python manage.py runserver
   ```

## 🌐 API-Dokumentation
Die RESTful API des Backends ermöglicht den Zugriff auf Nachrichtenartikel und Veranstaltungsdaten. 

## 💡 Mitwirken
Wir freuen uns über Beiträge und Verbesserungsvorschläge! 


## 👥 Kontakt
Falls du Fragen hast oder zur Weiterentwicklung beitragen möchtest, melde dich gerne über unser [GitHub Issues](https://github.com/dein-account/molo-news-backend/issues) oder kontaktiere uns per E-Mail unter `kontakt@molo.news`.

Viel Spaß beim Entwickeln! 🌟

