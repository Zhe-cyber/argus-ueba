"""
test_normalizer.py — pytest suite for the multi-cloud log normalization layer.

Run:
    pytest backend/tests/test_normalizer.py -v
"""

import sys
import os
import pytest

# Allow importing from the backend package regardless of cwd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.normalizer import (
    normalize,
    REQUIRED_FIELDS,
    SOURCE_AWS,
    SOURCE_AZURE,
    SOURCE_CERT_LOGON,
    SOURCE_CERT_FILE,
    SOURCE_CERT_DEVICE,
    SOURCE_CERT_EMAIL,
    SOURCE_CERT_HTTP,
    parse_aws_cloudtrail,
    parse_azure_ad,
    parse_cert_logon,
    parse_cert_file,
    parse_cert_device,
    parse_cert_email,
    parse_cert_http,
)


# ---------------------------------------------------------------------------
# Sample events (realistic payloads)
# ---------------------------------------------------------------------------

AWS_EVENT = {
    "eventVersion": "1.08",
    "userIdentity": {
        "type": "IAMUser",
        "principalId": "AIDA1234567890EXAMPLE",
        "arn": "arn:aws:iam::123456789012:user/alice",
        "accountId": "123456789012",
        "userName": "alice",
    },
    "eventTime": "2024-03-15T10:23:45Z",
    "eventSource": "s3.amazonaws.com",
    "eventName": "GetObject",
    "awsRegion": "us-east-1",
    "sourceIPAddress": "203.0.113.42",
    "userAgent": "aws-cli/2.13.0",
    "requestParameters": {
        "bucketName": "prod-data-bucket",
        "key": "exports/report_q1.csv",
    },
    "responseElements": None,
    "eventID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
}

AZURE_EVENT = {
    "id": "b3d4e5f6-7890-abcd-ef12-345678901234",
    "createdDateTime": "2024-03-15T09:11:22Z",
    "userDisplayName": "Bob Smith",
    "userPrincipalName": "bob@contoso.com",
    "userId": "a1b2c3d4-0000-1111-2222-333344445555",
    "appId": "00000002-0000-0000-c000-000000000000",
    "appDisplayName": "Microsoft Teams",
    "ipAddress": "198.51.100.17",
    "clientAppUsed": "Browser",
    "correlationId": "c0rr3l4t10n",
    "conditionalAccessStatus": "success",
    "resourceDisplayName": "Microsoft Teams",
    "status": {"errorCode": 0, "failureReason": None},
    "deviceDetail": {"deviceId": "", "displayName": "", "operatingSystem": "Windows 10"},
    "location": {"city": "Singapore", "countryOrRegion": "SG"},
}

CERT_LOGON_EVENT = {
    "id": "LOG001",
    "date": "2024-01-10 08:02:14",
    "user": "carol",
    "pc": "WS-CAROL-01",
    "activity": "Logon",
}

CERT_FILE_EVENT = {
    "id": "FILE042",
    "date": "2024-01-10 13:47:30",
    "user": "dave",
    "pc": "WS-DAVE-01",
    "filename": "C:\\Users\\dave\\Documents\\q4_strategy.docx",
    "activity": "File Copy",
    "to_removable_media": True,
    "from_removable_media": False,
}

CERT_DEVICE_EVENT = {
    "id": "DEV007",
    "date": "2024-01-10 08:00:55",
    "user": "eve",
    "pc": "WS-EVE-02",
    "activity": "Connect",
}

CERT_EMAIL_EVENT = {
    "id": "MAIL099",
    "date": "2024-01-10 17:52:01",
    "user": "frank",
    "pc": "WS-FRANK-01",
    "to": "competitor@external.com",
    "cc": "",
    "bcc": "",
    "from": "frank@company.com",
    "activity": "Send",
    "size": 1048576,
    "attachments": "salary_data_2024.xlsx",
    "content": "Please find attached.",
}

CERT_HTTP_EVENT = {
    "id": "HTTP123",
    "date": "2024-01-10 14:22:00",
    "user": "grace",
    "pc": "WS-GRACE-03",
    "url": "https://www.dropbox.com/upload",
    "activity": "WWW Upload",
    "content": "binary payload",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_required_fields(result: dict, expected_source: str) -> None:
    """Assert that all 8 required fields are present and types are correct."""
    for field in REQUIRED_FIELDS:
        assert field in result, f"Missing field: {field!r}"
    assert result["source"] == expected_source
    assert isinstance(result["timestamp"], str)
    assert isinstance(result["user"], str)
    assert isinstance(result["action"], str)
    assert isinstance(result["resource"], str)
    assert isinstance(result["ip_address"], str)
    assert isinstance(result["metadata"], dict)
    assert isinstance(result["raw"], dict)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAwsCloudTrail:
    def test_aws_cloudtrail_parsing(self):
        result = parse_aws_cloudtrail(AWS_EVENT)
        assert_required_fields(result, SOURCE_AWS)
        assert result["timestamp"] == "2024-03-15T10:23:45Z"
        assert result["user"] == "alice"
        assert result["action"] == "GetObject"
        assert result["resource"] == "prod-data-bucket"
        assert result["ip_address"] == "203.0.113.42"

    def test_aws_metadata_contains_event_id(self):
        result = parse_aws_cloudtrail(AWS_EVENT)
        assert result["metadata"]["eventID"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert result["metadata"]["awsRegion"] == "us-east-1"

    def test_aws_raw_is_original_event(self):
        result = parse_aws_cloudtrail(AWS_EVENT)
        assert result["raw"] is AWS_EVENT

    def test_aws_fallback_to_principal_id_when_no_username(self):
        event = {**AWS_EVENT, "userIdentity": {"principalId": "ANON123"}}
        result = parse_aws_cloudtrail(event)
        assert result["user"] == "ANON123"

    def test_aws_missing_ip_returns_empty_string(self):
        event = {k: v for k, v in AWS_EVENT.items() if k != "sourceIPAddress"}
        result = parse_aws_cloudtrail(event)
        assert result["ip_address"] == ""


class TestAzureAD:
    def test_azure_ad_parsing(self):
        result = parse_azure_ad(AZURE_EVENT)
        assert_required_fields(result, SOURCE_AZURE)
        assert result["timestamp"] == "2024-03-15T09:11:22Z"
        assert result["user"] == "bob@contoso.com"
        assert result["action"] == "Microsoft Teams"
        assert result["resource"] == "Microsoft Teams"
        assert result["ip_address"] == "198.51.100.17"

    def test_azure_metadata_correlation_id(self):
        result = parse_azure_ad(AZURE_EVENT)
        assert result["metadata"]["correlationId"] == "c0rr3l4t10n"

    def test_azure_raw_is_original_event(self):
        result = parse_azure_ad(AZURE_EVENT)
        assert result["raw"] is AZURE_EVENT

    def test_azure_missing_ip_returns_empty_string(self):
        event = {k: v for k, v in AZURE_EVENT.items() if k != "ipAddress"}
        result = parse_azure_ad(event)
        assert result["ip_address"] == ""


class TestCertLogon:
    def test_cert_logon_parsing(self):
        result = parse_cert_logon(CERT_LOGON_EVENT)
        assert_required_fields(result, SOURCE_CERT_LOGON)
        assert result["timestamp"] == "2024-01-10 08:02:14"
        assert result["user"] == "carol"
        assert "Logon" in result["action"]
        assert result["resource"] == "WS-CAROL-01"
        assert result["ip_address"] == ""

    def test_cert_logon_action_includes_activity(self):
        result = parse_cert_logon(CERT_LOGON_EVENT)
        assert result["action"] == "Logon:Logon"

    def test_cert_logon_metadata_contains_pc(self):
        result = parse_cert_logon(CERT_LOGON_EVENT)
        assert result["metadata"]["pc"] == "WS-CAROL-01"


class TestCertFile:
    def test_cert_file_parsing(self):
        result = parse_cert_file(CERT_FILE_EVENT)
        assert_required_fields(result, SOURCE_CERT_FILE)
        assert result["timestamp"] == "2024-01-10 13:47:30"
        assert result["user"] == "dave"
        assert result["action"] == "File Copy"
        assert "q4_strategy.docx" in result["resource"]
        assert result["ip_address"] == ""

    def test_cert_file_removable_media_in_metadata(self):
        result = parse_cert_file(CERT_FILE_EVENT)
        assert result["metadata"]["to_removable_media"] is True
        assert result["metadata"]["from_removable_media"] is False


class TestCertDevice:
    def test_cert_device_parsing(self):
        result = parse_cert_device(CERT_DEVICE_EVENT)
        assert_required_fields(result, SOURCE_CERT_DEVICE)
        assert result["timestamp"] == "2024-01-10 08:00:55"
        assert result["user"] == "eve"
        assert result["action"] == "Device:Connect"
        assert result["resource"] == "WS-EVE-02"
        assert result["ip_address"] == ""


class TestCertEmail:
    def test_cert_email_parsing(self):
        result = parse_cert_email(CERT_EMAIL_EVENT)
        assert_required_fields(result, SOURCE_CERT_EMAIL)
        assert result["timestamp"] == "2024-01-10 17:52:01"
        assert result["user"] == "frank"
        assert result["action"] == "Send"
        assert "competitor@external.com" in result["resource"]
        assert result["ip_address"] == ""

    def test_cert_email_attachment_in_metadata(self):
        result = parse_cert_email(CERT_EMAIL_EVENT)
        assert result["metadata"]["attachments"] == "salary_data_2024.xlsx"


class TestCertHttp:
    def test_cert_http_parsing(self):
        result = parse_cert_http(CERT_HTTP_EVENT)
        assert_required_fields(result, SOURCE_CERT_HTTP)
        assert result["timestamp"] == "2024-01-10 14:22:00"
        assert result["user"] == "grace"
        assert result["action"] == "WWW Upload"
        assert result["resource"] == "https://www.dropbox.com/upload"
        assert result["ip_address"] == ""


class TestNormalizeDispatcher:
    def test_normalize_routes_aws(self):
        result = normalize(AWS_EVENT, SOURCE_AWS)
        assert result["source"] == SOURCE_AWS

    def test_normalize_routes_azure(self):
        result = normalize(AZURE_EVENT, SOURCE_AZURE)
        assert result["source"] == SOURCE_AZURE

    def test_normalize_routes_cert_logon(self):
        result = normalize(CERT_LOGON_EVENT, SOURCE_CERT_LOGON)
        assert result["source"] == SOURCE_CERT_LOGON

    def test_unknown_source_raises_error(self):
        with pytest.raises(ValueError, match="Unknown source"):
            normalize(AWS_EVENT, "unknown_cloud_provider")

    def test_non_dict_event_raises_type_error(self):
        with pytest.raises(TypeError, match="event must be a dict"):
            normalize("not a dict", SOURCE_AWS)  # type: ignore[arg-type]

    def test_all_parsers_return_required_fields(self):
        """Every parser must produce all 8 required fields with correct types."""
        cases = [
            (AWS_EVENT,          SOURCE_AWS),
            (AZURE_EVENT,        SOURCE_AZURE),
            (CERT_LOGON_EVENT,   SOURCE_CERT_LOGON),
            (CERT_FILE_EVENT,    SOURCE_CERT_FILE),
            (CERT_DEVICE_EVENT,  SOURCE_CERT_DEVICE),
            (CERT_EMAIL_EVENT,   SOURCE_CERT_EMAIL),
            (CERT_HTTP_EVENT,    SOURCE_CERT_HTTP),
        ]
        for event, source in cases:
            result = normalize(event, source)
            assert_required_fields(result, source), f"Failed for source={source}"

    def test_raw_field_preserves_original_event(self):
        """The 'raw' field must be the exact same dict object as the input."""
        result = normalize(AWS_EVENT, SOURCE_AWS)
        assert result["raw"] is AWS_EVENT
