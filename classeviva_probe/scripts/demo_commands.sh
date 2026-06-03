#!/usr/bin/env bash
set -euo pipefail

cv-probe smoke
cv-probe info
cv-probe documenti
cv-probe assenze
cv-probe lezioni-giorno --date 2026-04-10
