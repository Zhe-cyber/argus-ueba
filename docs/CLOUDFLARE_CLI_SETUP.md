# Cloudflare Access: local CLI authentication

Zero Trust Free enrollment is complete. Access applications and usable login logs
have not yet been verified. Wrangler's available OAuth scopes do not include
Access audit logs, so use a separate API token for these API calls.

1. Open https://dash.cloudflare.com/profile/api-tokens and create a custom **user
   API token** named `argus-access-inspect`.
2. Select account permissions **Access: Apps Read**, **Access: Identity Providers
   Read**, and **Access: Audit Logs Read**. Restrict account resources to your
   intended Cloudflare account. Use a short expiry suitable for the competition.
3. In your own local PowerShell, run the following with your account ID:

   ```powershell
   powershell -NoProfile -File .\scripts\cloudflare_inspect.ps1 -AccountId YOUR_32_CHARACTER_ACCOUNT_ID -SaveToken
   ```

4. Paste the token at the hidden prompt. Do not paste it into chat, command-line
   arguments, environment files, or source control. Clear the clipboard afterwards.
   Subsequent runs omit `-SaveToken`.

The helper verifies the token and stores its encrypted representation under
`%LOCALAPPDATA%\Argus\credentials\cloudflare-ACCOUNT_ID.dpapi`. Windows DPAPI binds
decryption to your current Windows user; processes running as that user can still
access it. It never stores plaintext in the repository. Re-running `-SaveToken`
replaces the local saved credential, and does not revoke the previous remote token.

Inspection reads a one-record application sample, identity-provider count and a
one-record authentication-log sample. It prints counts only. A zero sample means
the API returned no records, not that the detector is working. A failure means
coverage is unverified; a saved valid token may still lack an endpoint permission.

This token cannot provision applications. If an application is absent, use a
separate temporary setup credential to configure an Access-protected test app and
an explicit allow policy. The long-running collector should use only **Access:
Audit Logs Read**. Neither the app nor its policy has been created by this helper.

Authentication logs record login attempts, not actions later taken inside the app.
No real logs should enter Argus until duplicate-safe ingestion and access controls
are ready.

References:
- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://developers.cloudflare.com/cloudflare-one/insights/logs/dashboard-logs/access-authentication-logs/
- https://developers.cloudflare.com/workers/wrangler/commands/general/
