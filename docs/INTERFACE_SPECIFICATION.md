# HL7 interface specification

## Envelope

Inbound and outbound messages use MLLP framing: vertical tab (0x0B), HL7 ER7 payload, file separator (0x1C), and carriage return (0x0D). UTF-8 is the default encoding. The listener rejects a frame larger than the configured maximum.

## Supported messages

| Message | Required content | Transformations |
| --- | --- | --- |
| ADT^A01/A03/A04/A08 | PID and patient identity fields | name, sex, assigning authority, and PV1 defaults |
| ORM^O01 | PID, ORC, and OBR | placer number synchronization and local-to-LOINC mapping |
| ORU^R01 | PID, OBR, and one or more OBX segments | missing result status defaults to F; critical flags set route metadata |

The validator accepts HL7 versions 2.3, 2.3.1, 2.4, 2.5, and 2.5.1. Required field errors use code 101, data type errors use 102, table violations use 103, unsupported message types use 200, unsupported versions use 203, and replay or internal processing failures use 207.

## Acknowledgments

The ACK MSH reverses the inbound sending and receiving applications and facilities. MSA-1 is AA for successful delivery, AE for application or downstream failure, and AR for a malformed or unsupported request. MSA-2 contains the original MSH-10. AE and AR responses include ERR with the failing location, code, message, and severity.

## Data handling

DLQ JSON records contain the raw ER7 message and may contain protected health information. Protect the directory with the same controls as the interface host, limit retention, and do not copy records into general-purpose logs.
