"""Provision only a fail-closed Access test Worker; inspect by default.

Uses the Windows current-user DPAPI credential saved by cloudflare_inspect.ps1.
Never accepts credentials as arguments or prints API response bodies.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
NAME = "argus-access-demo"
APP_NAME = "Argus Access authentication demo"


class SetupError(Exception):
    pass


class APIError(SetupError):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_token(account: str) -> str:
    if sys.platform != "win32":
        raise SetupError("This credential loader requires Windows current-user DPAPI.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    try:
        path = Path(os.environ["LOCALAPPDATA"]) / "Argus" / "credentials" / f"cloudflare-{account}.dpapi"
        ciphertext = bytes.fromhex(path.read_text(encoding="ascii").strip())
        buffer = (ctypes.c_ubyte * len(ciphertext)).from_buffer_copy(ciphertext)
        source = Blob(len(ciphertext), buffer)
        output = Blob()
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
                                            ctypes.c_void_p, ctypes.c_void_p,
                                            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        crypt.CryptUnprotectData.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1,
                                       ctypes.byref(output)):
            raise SetupError("Windows could not decrypt the saved credential.")
        try:
            token = ctypes.string_at(output.data, output.size).decode("utf-16-le")
        finally:
            ctypes.memset(output.data, 0, output.size)
            kernel.LocalFree(output.data)
        if not token.strip():
            raise SetupError("Saved credential is empty.")
        return token
    except SetupError:
        raise
    except Exception:
        raise SetupError("Cannot read the locally saved DPAPI credential.") from None


class Cloudflare:
    def __init__(self, account: str, token: str):
        self.account = account
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def call(self, method: str, path: str, body=None, content_type="application/json"):
        if not path.startswith(("workers/", "access/")):
            raise SetupError("Unsupported API path.")
        data = body if isinstance(body, bytes) else (
            json.dumps(body).encode() if body is not None else None
        )
        request = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/accounts/{self.account}/{path}",
            data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": content_type},
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            codes = []
            try:
                codes = [item["code"] for item in json.load(error).get("errors", [])
                         if isinstance(item.get("code"), int)]
            except Exception:
                pass
            raise APIError(f"{method} {path}: HTTP {error.code}; API codes {codes}", error.code) from None
        except Exception:
            raise SetupError(f"{method} {path}: request failed; response not displayed.") from None
        if not result.get("success"):
            raise SetupError(f"{method} {path}: API rejected request; response not displayed.")
        return result["result"]

    def all(self, path: str):
        records = []
        for page in range(1, 101):
            batch = self.call("GET", f"{path}?per_page=100&page={page}")
            if not isinstance(batch, list):
                raise SetupError("Unexpected list response.")
            records.extend(batch)
            if len(batch) < 100:
                return records
        raise SetupError("Resource listing exceeded safety limit; refusing partial inspection.")


def multipart(metadata: dict, source: str):
    boundary = "argus-" + uuid.uuid4().hex
    parts = []
    for name, mime, content in [("metadata", "application/json", json.dumps(metadata)),
                                ("worker.mjs", "application/javascript+module", source)]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                     f'filename="{name}"\r\nContent-Type: {mime}\r\n\r\n{content}\r\n')
    return ("".join(parts) + f"--{boundary}--\r\n").encode(), f"multipart/form-data; boundary={boundary}"


def provision(api: Cloudflare, email: str, deploy=False, new_subdomain=None):
    # Complete read-only preflight before creating anything.
    scripts = api.all("workers/scripts")
    apps = api.all("access/apps")
    if any(item.get("id") == NAME for item in scripts):
        raise SetupError("Same-name Worker already exists; inspect it manually before retrying.")
    if any(item.get("name") == APP_NAME for item in apps):
        raise SetupError("Same-name Access app already exists; inspect it manually before retrying.")
    try:
        subdomain = api.call("GET", "workers/subdomain").get("subdomain")
    except APIError as error:
        if error.status != 404 or not new_subdomain:
            raise
        subdomain = None
    if not subdomain and not new_subdomain:
        raise SetupError("No registered workers.dev subdomain; specify --new-subdomain.")
    if subdomain and new_subdomain and subdomain != new_subdomain:
        raise SetupError("Refusing to rename an existing workers.dev subdomain.")
    planned_host = f"{NAME}.{subdomain or new_subdomain}.workers.dev"
    if any(item.get("domain") == planned_host for item in apps):
        raise SetupError("An Access application already protects this hostname; inspect it manually.")
    if not deploy:
        return {"mode": "inspect", "ready": True, "worker": NAME, "changes": 0}
    if not subdomain:
        subdomain = api.call("PUT", "workers/subdomain", {"subdomain": new_subdomain})["subdomain"]
    host = f"{NAME}.{subdomain}.workers.dev"
    metadata = {
        # Pin an established runtime baseline; the provider rejects future dates.
        "main_module": "worker.mjs", "compatibility_date": "2025-01-01",
        "bindings": [{"name": "ALLOWED_EMAIL", "type": "plain_text", "text": email}],
    }
    body, content_type = multipart(metadata, (ROOT / "infra/cloudflare-access-demo.mjs").read_text())
    api.call("PUT", f"workers/scripts/{NAME}", body, content_type)
    # Worker also checks ctx.access and the approved email: safe during propagation.
    api.call("POST", f"workers/scripts/{NAME}/subdomain",
             {"enabled": False, "previews_enabled": False})
    app = api.call("POST", "access/apps", {
        "type": "self_hosted", "name": APP_NAME, "domain": host,
        "session_duration": "1h", "app_launcher_visible": False,
        "policies": [{"name": "Approved investigator only", "decision": "allow",
                      "include": [{"email": {"email": email}}]}],
    })
    policies = api.call("GET", f"access/apps/{app['id']}/policies")
    if (len(policies) != 1 or policies[0].get("decision") != "allow"
            or policies[0].get("include") != [{"email": {"email": email}}]
            or policies[0].get("exclude") or policies[0].get("require")):
        raise SetupError("Policy read-back mismatch; route remains disabled.")
    api.call("POST", f"workers/scripts/{NAME}/subdomain",
             {"enabled": True, "previews_enabled": False})
    return {"mode": "deployed", "url": f"https://{host}", "app_id": app["id"],
            "login_evidence": "pending user sign-in"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--allowed-email", required=True)
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--new-subdomain")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", args.account_id):
        parser.error("account ID must be 32 hexadecimal characters")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", args.allowed_email):
        parser.error("a single valid email is required")
    if args.new_subdomain and not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,50}[a-z0-9])?", args.new_subdomain):
        parser.error("invalid new subdomain")
    try:
        api = Cloudflare(args.account_id.lower(), load_token(args.account_id.lower()))
        result = provision(api, args.allowed_email.lower(), args.deploy, args.new_subdomain)
        print(json.dumps(result))
        return 0
    except SetupError as error:
        print(f"Setup stopped: {error}. Partial resources are preserved for inspection.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
