# Tutor Digitale Studio AI

Prototipo web nato dal progetto `ClasseViva Probe` e trasformato in una web app più vicina al concept:

- organizzazione di compiti e verifiche
- pianificazione automatica dello studio
- monitoraggio del rendimento scolastico
- suggerimenti personalizzati in stile tutor digitale
- classifica utenti con punteggi e premi

L'app continua a usare i dati scolastici come sorgente, ma non si limita più a mostrare JSON grezzi.

## Pagine principali

- `/dashboard`: panoramica generale con task, piano breve, suggerimenti e preview dati scolastici
- `/tutor`: chat con tutor AI contestuale ai dati scolastici e al piano di studio
- `/planner`: piano di studio settimanale generato automaticamente
- `/attivita`: gestione compiti, verifiche, ripassi e stato avanzamento
- `/rendimento`: medie per materia, voti, assenze e note
- `/bacheca`: circolari e allegati con preview interna
- `/profilo`: obiettivi di studio, modalità DSA/standard/intensiva e classifica

## Componenti tecnici introdotti

- database locale SQLite per profili e attività
- motore base di pianificazione automatica
- sistema di suggerimenti personalizzati
- integrazione opzionale con chat AI reale via Gemini
- classifica con punteggi
- anteprima interna allegati circolari, con supporto migliore per PDF, immagini, testo e `.docx`

## Setup rapido

```bash
cd /percorso/del/progetto/classeviva_probe
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e . --no-build-isolation
cp .env.example .env
```

Compila `.env`:

```env
CV_USERNAME=il_tuo_username
CV_PASSWORD=la_tua_password
AI_PROVIDER=gemini
GEMINI_API_KEY=la_tua_api_key_gratuita
GEMINI_MODEL=gemini-2.5-flash
```

## Avvio

```bash
source .venv/bin/activate
cv-probe-web
```

Di default:

```text
http://127.0.0.1:8765
```

Per VPS o LAN:

```bash
cv-probe-web --host 0.0.0.0 --port 8765
```

## Note utili

- Le attività manuali vengono salvate in un database locale `.cvprobe.sqlite3`
- Senza `GEMINI_API_KEY` la chat resta disponibile in fallback locale, ma per il tutor AI reale va configurata la chiave
- Se alcuni endpoint ClasseViva falliscono, l'app continua comunque a funzionare sulle altre sezioni
- Gli allegati circolari non vengono più gestiti solo come download: l'app prova ad aprirli nel viewer interno

## CLI legacy

La CLI di debug è ancora disponibile:

```bash
cv-probe smoke
cv-probe info
cv-probe bacheca
```
