FROM python:3.14.2-slim-bookworm
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY manage.py ./
COPY attendance_project/ ./attendance_project
COPY bus_tracker_app/ ./bus_tracker_app