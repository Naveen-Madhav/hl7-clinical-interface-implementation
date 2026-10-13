# HL7 verification runbook

From the project directory, run the unit and integration suite:

    python3 -m unittest discover -s tests -v

Run the representative accepted transactions through an isolated runtime directory:

    python3 scripts/run_verification.py

For a live MLLP exchange, start the two local downstream listeners, start the interface server, then send a sample message with mllp_client.py. The server writes failures to the configured DLQ directory; the default runtime paths are excluded from source control.

## Useful checks

- Confirm the ACK MSA-1 and MSA-2 values match the expected result and inbound control ID.
- Inspect ERR only for AE and AR responses.
- Check the transformed message received by the recording or downstream listener when testing LOINC mapping or critical-result fan-out.
- Use a temporary deduplication file for repeatable test runs.

The sample messages use synthetic identifiers. Never put production patient data in this repository or in an unprotected test output directory.
