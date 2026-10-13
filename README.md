# HL7 Clinical Interface Implementation

A Python HL7 v2 broker for patient registration, clinical orders, and results, with message validation, workflow mapping, and correlated acknowledgments.

## Integration problem

Clinical applications need a consistent way to exchange patient events, orders, and results. An interface must recognize the workflow, check required fields, translate known local codes, and distinguish accepted delivery from a rejected or unavailable destination. This project implements those boundaries with local reference endpoints and explicit error responses.

## Architecture and data flow

```text
EHR / CPOE / LIS -> MLLP listener -> ER7 parser -> validation -> transformation -> routing
                                                                               |-> LIS orders
                                                                               |-> clinical repository
                                                                               |-> critical-result alert endpoint
                    <- correlated ACK <- delivery outcome                      |-> DLQ on failure
```

The processing service checks the sending application and MSH-10 replay key, validates the message, applies workflow mappings, and resolves destinations from JSON configuration. It returns AA after downstream delivery succeeds and records the control ID in a persistent cache. Invalid or failed transactions receive AE or AR and a JSON dead-letter record containing the payload and diagnostics.

| Workflow | Implemented behavior | Destination |
| --- | --- | --- |
| `ADT^A01`, `A03`, `A04`, `A08` | Normalize names, sex codes, assigning authority, and selected visit defaults | Clinical data repository |
| `ORM^O01` | Synchronize placer order identifiers and translate known local test codes to LOINC | Laboratory information system |
| `ORU^R01` | Default missing observation status to final; detect critical flags in the transformation code | Repository, plus alert endpoint for critical results |

## Components and standards

| Path | Responsibility |
| --- | --- |
| `engine/parser.py`, `engine/mllp.py` | Delimiter-aware ER7 parsing, serialization, and MLLP framing |
| `engine/validator.py`, `engine/transformer.py` | Supported-message checks and workflow-specific field changes |
| `engine/router.py`, `engine/pipeline.py` | Route selection and downstream delivery |
| `engine/server.py`, `engine/ack_handler.py` | Bounded listener and ACK/ERR construction |
| `engine/deduplication.py`, `engine/exception_manager.py` | TTL replay cache and failure persistence |
| `config/` | Local endpoints, routing rules, and a field mapping reference |
| `scripts/` | MLLP sender, mock LIS/CDR endpoints, and in-process verification |
| `sample_messages/`, `tests/` | Nominal/error fixtures and unit/integration tests |

The executable engine uses Python's standard library and requires no third-party packages. It accepts the configured HL7 versions 2.3, 2.3.1, 2.4, 2.5, and 2.5.1 for the supported workflows. It uses ER7 encoding, MLLP over TCP, ACK/ERR responses, and a limited local-code-to-LOINC table.

## Quickstart

From this repository's root, with Python 3.11 or later:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/run_verification.py
```

The verification script processes the eight nominal messages with an in-memory recording dispatcher. It checks acceptance through the processing service without opening sockets. Its state and DLQ are temporary. The test suite covers parsing, framing, validation errors, transformations, routing, acknowledgments, replay persistence, and simulated delivery failures.

To explore actual MLLP connections, run each of the first three commands in a separate terminal, then send a message with the fourth:

```bash
python3 scripts/mock_downstream_lis.py --port 2576
python3 scripts/mock_downstream_cdr.py --cdr-port 2577 --stat-port 2578
python3 -c 'import json, threading; from engine.server import HL7InterfaceEngineServer; config=json.load(open("config/interface_config.json")); server=HL7InterfaceEngineServer(config); server.start(); threading.Event().wait()'
python3 scripts/mllp_client.py sample_messages/nominal/ADT_A01_admit.hl7 --port 2575
```

Default endpoints use loopback, with inbound port 2575, LIS 2576, repository 2577, and alerts 2578. Reusing a successfully processed MSH-10 returns AR until it expires from the replay cache. Runtime `logs/` and `dlq/` files remain local.

Read the [interface specification](docs/INTERFACE_SPECIFICATION.md), [architecture](docs/ARCHITECTURE_AND_DATA_FLOW.md), and [test runbook](docs/TEST_EXECUTION_RUNBOOK.md) for the processing contract. The [Rhapsody deployment mapping](docs/RHAPSODY_CONFIGURATION_GUIDE.md) explains how the Python boundaries could map to another engine.

## Sample data

The checked-in messages and test payloads use synthetic patient identifiers, demographics, orders, and observations. They contain no patient data. Vendor-style sending application names are example values, not evidence of a connection to a live EHR or LIS. `sample_messages/nominal/` contains eight workflow examples; `error_scenarios/` contains seven examples for missing identifiers, invalid data, unsupported messages or versions, and replay rejection.

The duplicate-control-ID sample intentionally reuses the admit sample's control ID. Send the successful admit message first to observe replay rejection. Other malformed samples exercise AE/AR behavior. Do not replace these fixtures with patient messages.

## Honest Scope and Limitations

- This is a local reference implementation, not a live Epic, Cerner, or hospital deployment. It does not claim a business outcome, throughput benchmark, or regulatory certification.
- MLLP is unencrypted. Sender-name allowlisting does not authenticate a remote system, and the `require_tls` field does not enable TLS in the listener.
- Validation covers selected fields and supported structures, not the full HL7 standard. Transformations and LOINC mappings are implemented in Python; `field_mappings.json` is a reference matrix rather than a general mapping runtime or complete version converter.
- Delivery is synchronous and has one attempt per destination. Retry/backoff and alert settings in configuration are not implemented as automatic replay or notifications.
- The replay cache is keyed by MSH-10 and uses a local file. It does not provide atomic duplicate suppression across concurrent transactions or shared state across instances. Partial fan-out failure can deliver to one destination and deliver there again on retry.
- DLQ records retain full payloads. A real deployment requires protected storage, retention controls, delivery reconciliation, and operational monitoring.
- No Mirth Connect channel export or executable Rhapsody project is included. The Rhapsody guide is a deployment mapping only.

## Author and license

Naveen Madhav | [LinkedIn](https://linkedin.com/in/naveenmadhav)

Licensed under the [MIT License](LICENSE).
