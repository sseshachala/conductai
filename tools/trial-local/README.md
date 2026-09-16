# Local Trial Check

Requires the running `conduct-e2e` security harness and its separate Clerk test
instance. Uses its existing API image, PostgreSQL, Redis, and encryption key;
mounts the current receipt URL builder. No production keys are accepted.

```sh
rtk proxy python3.11 tools/trial-local/start.py
rtk proxy python3.11 tools/trial-local/start.py --web-only
```

The second command runs the current web source on `http://localhost:3107`
with the local API at `http://localhost:3110` and the same Clerk test instance.
It does not read production credential files. Port 3107 must be free.

Submit a trial to `POST http://localhost:3110/guard/trial/provision` with
`email` and `company` fields. Open `http://localhost:3110/__trial/inbox`, follow
the captured email link, and click Verify email. Provisioning uses the real
local API and database; Clerk operations use the external test instance.
Email delivery is replaced with an in-memory capture, not a real email send.

The inbox contains one-use verification links: keep it local. It is exposed
only on loopback and is never mounted in production. Restarting the container
clears the inbox. Local database changes and Clerk test users persist.
The launcher refuses an existing container name rather than replacing it.

Stop the web process with Ctrl-C. Stop the trial API with:

```sh
rtk docker stop conduct-trial-local-api
```

This check does not establish production email delivery or model inference.
