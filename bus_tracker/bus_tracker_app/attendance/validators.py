"""Validate the small, untrusted JSON commands used by attendance endpoints."""

import json


MAX_PAYLOAD_BYTES = 4096


class AttendancePayloadError(ValueError):
    """The client supplied an invalid attendance command."""


def _unique_object(pairs):
    payload = {}
    for key, value in pairs:
        if key in payload:
            raise AttendancePayloadError(f"Duplicate field: {key}.")
        payload[key] = value
    return payload


def _parse_command(raw_body, field):
    if len(raw_body) > MAX_PAYLOAD_BYTES:
        raise AttendancePayloadError("The request body is too large.")
    try:
        payload = json.loads(raw_body.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise AttendancePayloadError("The request body must contain valid JSON.") from error
    if not isinstance(payload, dict) or set(payload) != {field}:
        raise AttendancePayloadError(f"The JSON object must contain only '{field}'.")
    return payload[field]


def parse_absent_json(raw_body):
    absent = _parse_command(raw_body, "absent")
    if type(absent) is not bool:
        raise AttendancePayloadError("absent must be a JSON Boolean: true or false.")
    return absent


def parse_attendance_json(raw_body):
    status = _parse_command(raw_body, "status")
    if not isinstance(status, str) or status not in {"present", "absent"}:
        raise AttendancePayloadError("status must be 'present' or 'absent'.")
    return status
