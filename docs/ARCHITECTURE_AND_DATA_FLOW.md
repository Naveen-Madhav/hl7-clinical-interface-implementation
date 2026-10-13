# HL7 interface architecture

The engine sits between source clinical systems and downstream repositories. Its transport, parsing, validation, workflow enrichment, routing, delivery, acknowledgment, and failure persistence boundaries are separate so each can be tested without opening a socket.

## Processing path

    MLLP listener -> ER7 parser -> validator -> transformer -> router
                                                       -> downstream MLLP
                                                       -> DLQ on failure

The listener owns connection limits, idle timeouts, and frame size. The processing service owns one message transaction. It validates before transformation, delivers before committing the MSH-10 replay key, and returns an ACK that correlates to the inbound control ID.

## Destination policy

| Message | Condition | Destination |
| --- | --- | --- |
| ADT^A01/A03/A04/A08 | any valid event | CDR |
| ORM^O01 | valid order | LIS |
| ORU^R01 | no critical flag | CDR |
| ORU^R01 | HH, LL, CRIT, or PANIC | CDR and alert service |

The configured routing rules are authoritative. The router has a small built-in default for callers that construct it without a configuration file; the documented local startup supplies the JSON configuration.

## Failure handling

Malformed frames or parse failures receive AR. Validation errors map to AE or AR using the error severity and Table 0357 code. Downstream connection failures and non-AA acknowledgments receive AE and are written to the DLQ with the transformed ER7 payload.

The persistent replay cache is runtime state. It is bounded and TTL-pruned, and writes use a temporary file followed by replacement to avoid partially written state after a process failure.
