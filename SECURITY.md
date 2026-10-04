# Private data and safe sharing

Configure your own TV, optional notification topic, and pairing tokens locally.
The repository contains placeholders and fabricated test values only.

Never commit or upload:

- `config.json`, other private runtime configurations, or `.env` files.
- Anything in `private/`, including pairing tokens, saved TV identities, original
  settings, controller state, or diagnostic records.
- Notification topic URLs, authentication tokens, private keys, certificates,
  SSH configuration, local network addresses, or device MAC addresses.
- Whole working-directory ZIPs, logs, SDK folders, or research downloads.

`.gitignore` excludes common sensitive paths. It cannot remove a secret that was
already committed, and it cannot protect files added with `git add -f`. Review
the staged diff before every push. A local Gitleaks scan is useful, but also check
for personal device and network identifiers that generic scanners may not know.

The local client connects to the TV directly and accepts its self-signed
certificate. Keep control traffic on your trusted home network. Do not forward
the TV's control ports to the internet.

Share the redacted output from `inspect`, after reviewing it, instead of raw
device responses or private state files. Error logging avoids notification URLs
and tokens. Runtime configuration and raw diagnostic files still require care.

For a public bug report, include the model code, firmware version, redacted error
type, and steps to reproduce. Leave out tokens, topics, local addresses, Wi-Fi
details, device IDs, and screenshots containing those values.
