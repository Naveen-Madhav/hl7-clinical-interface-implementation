# Rhapsody deployment mapping

The Python engine is the executable reference for the interface behavior. A Rhapsody deployment can map the same boundaries to native communication points, filters, routes, and an error queue.

| Engine boundary | Rhapsody component |
| --- | --- |
| server.py and mllp.py | inbound TCP/IP server with MLLP framing |
| parser.py and validator.py | HL7 message definition and validation filters |
| transformer.py | workflow-specific JavaScript or mapping filter |
| router.py | content-based route |
| pipeline.py | route orchestration and outbound delivery |
| ack_handler.py | synchronous ACK response |
| exception_manager.py | error queue or protected file appender |

Configure inbound port 2575, LIS port 2576, CDR port 2577, and alert port 2578 only where those endpoints exist. Set the downstream retry and timeout policy in the target environment; do not treat the local JSON endpoints as production addresses.

The application ACK is returned after downstream delivery. If the target returns AE or AR, preserve the target response in the failure record and return AE to the original sender. Replay handling should use a shared durable store when multiple engine instances process the same source feed.
