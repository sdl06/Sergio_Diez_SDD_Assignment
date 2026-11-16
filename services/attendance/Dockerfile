FROM python:3.14.2-slim-bookworm
WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY manage.py ./
COPY attendance_project/ ./attendance_project
COPY bus_tracker_app/ ./bus_tracker_app

RUN useradd --system --user-group app && chown app:app /app
USER app

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
