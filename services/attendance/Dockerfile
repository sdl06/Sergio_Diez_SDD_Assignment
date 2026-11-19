FROM python:3.14.2-slim-bookworm
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg \
    && curl -fsSL \
        https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
        -o /tmp/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 unixodbc-dev \
    && rm /tmp/packages-microsoft-prod.deb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY manage.py ./
COPY attendance_project/ ./attendance_project
COPY bus_tracker_app/ ./bus_tracker_app
COPY --chmod=755 start.sh /app/start.sh

RUN useradd --system --user-group app && chown app:app /app
USER app

EXPOSE 8000
CMD ["/app/start.sh"]