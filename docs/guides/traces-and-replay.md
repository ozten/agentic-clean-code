# Capture the bug report nobody has time to write

A useful bug report contains the trigger, relevant context, steps to reproduce, expected behavior, and actual behavior. Boundary traces automatically capture much of the evidence that people otherwise reconstruct by hand. The reporter still needs to explain what they expected.

Capture interactions where code meets its environment: API requests and responses, storage operations, clock reads, and other relevant effects. Give each operation an identifier so a report can point to the corresponding evidence. Internal logs and spans can supplement these records.

## Recording during application use

Per-interface application configuration defaults to `recorder` in development and `pass-through` in production. A recorder delegates to the real adapter and captures the interaction; a playback adapter returns recorded results without delegating. “Replay” describes the process performed by the playback adapter.

Development therefore builds a pool of potential reproduction evidence during ordinary application use. Select and review recordings before promoting them into integration-test fixtures. Tests wire their playback and stub instances directly, independently of application profile defaults.

Production pass-through does not capture these boundary records. To investigate a production-only issue using them, explicitly configure a recorder for the relevant interface and operation under the project's capture policy.

## Trace directory and identifiers

Write traces beneath a configurable root directory, defaulting to `traces/`. Each boundary interaction has its own trace directory containing a GUID in its name. Serialize the complete interaction to JSON or another format that preserves the values needed for playback.

Use two identifiers with distinct purposes:

- `trace_id`: a GUID identifying this individual boundary interaction; include it in the directory name and serialized record.
- `global_trace_id`: a shared GUID identifying the larger operation. Propagate it across related calls, retries, background tasks, and service boundaries so their traces can be correlated. Generate it at the initiating entry point if no correlation context exists.

An illustrative layout:

```text
<configured-trace-root>/
  trace-65f36b55-02d8-44fc-bc9b-c855c9d81b90/
    trace.json
  trace-cc2c1e4d-a315-4244-9ea5-531fe7e5dc48/
    trace.json
```

The records in these separate directories can carry the same `global_trace_id`. Correlate using that field, rather than relying on directory enumeration order. An optional index can make lookup faster; the identifier remains in each record so an exported trace retains its context.

## Serialized record

Capture all interface inputs and outputs, including failed outcomes, together with metadata such as error codes, interface and operation names, timing, application revision, schema version, and correlation identifiers. Preserve type information needed for faithful playback. If an operation produces no output because it failed, represent that explicitly instead of inventing a successful response.

For example, the filesystem failure during the second API retry could produce:

```json
{
  "schema_version": 1,
  "trace_id": "cc2c1e4d-a315-4244-9ea5-531fe7e5dc48",
  "global_trace_id": "c35573c4-0d19-4418-9b8a-e8c88c30a534",
  "parent_trace_id": null,
  "interface": "filesystem",
  "operation": "write_file",
  "inputs": {
    "path": "results/report.json",
    "content": "{\"status\":\"ready\"}"
  },
  "outputs": null,
  "metadata": {
    "status": "error",
    "error_code": "DiskFull",
    "error_message": "No space left on device",
    "api_attempt": 3,
    "sequence": 7,
    "started_at": "2026-09-01T12:00:00Z",
    "duration_ms": 2,
    "application_revision": "example-revision",
    "complete": true
  }
}
```

Here `complete` means the interaction's outcome was captured, even though the operation failed. `parent_trace_id` is optional causal context; populate it when a parent interaction exists. A shared global ID groups related traces but does not by itself establish their order. Record parent/child or dependency relationships for concurrent work, along with useful sequence information.

Also capture the initiating action and relevant configuration so the correlated interactions can be replayed in context. Mark interactions that started but have no captured result as incomplete. A process can crash after an external effect and before its response is saved.

Publish completed serialized files atomically, for example using a temporary file followed by a rename on a filesystem that supports the required semantics. A GUID directory alone does not guarantee an atomic write or a complete recording.

Apply the project's sensitive-data policy to full payload capture: redact credentials and protected content before persistence or export, and make any omitted or transformed values explicit. Review fixtures before committing them publicly. If redaction removes information needed for playback, provide a safe equivalent or document the reproduction gap. Define retention for production captures.

## Start with one explicitly wired response

Playback does not require a general-purpose replay engine. The smallest integration or end-to-end test directly supplies one adapter with one expected request and one serialized response or error. The test chooses the fixture; the adapter never searches the trace directory for a likely match.

Validate the request and expected call count. Fail on a mismatch or an unexpected second call. If the scenario consists of several application invocations, wire a fresh adapter for each invocation. Two identical requests can therefore receive different responses in different invocations without ambiguity.

Only add ordered response lists or stateful matching when a test needs them. [WireMock scenarios](https://wiremock.org/docs/stateful-behaviour/) are an optional growth path for explicitly stateful services. The [contractor-payment example](../../examples/contractor-payment/README.md) needs only single-response wiring.

## From report to regression test

1. Use the reported global trace ID to collect related trace directories, then associate them with the revision, initiating action, and expected behavior.
2. Prepare a reviewed fixture containing the inputs and environment responses needed to reproduce it.
3. Run the relevant code with replay adapters and controlled time/randomness as needed. Replay must not perform recorded side effects such as sending a notification or charging a card.
4. Match the interface, method, and meaningful request fields. Define any normalization explicitly. Fail on mismatches, missing calls, and unexpected unused calls when the scenario requires complete consumption. Never fall back to a live service.
5. Confirm that an assertion of the expected behavior fails on the buggy version and passes with the fix. Keep that assertion and fixture as a regression test.

Recordings reproduce captured responses; they do not prove those responses were correct or that the live service still behaves that way. Version fixtures and review changes when contracts evolve. Sanitization may remove information necessary for reproduction; document that limitation or use a synthetic equivalent.

## Choose a useful level of replay

Interface-level replay is useful for reproducing how the application reacted to environmental inputs. Transport-level replay can additionally exercise request encoding and response decoding. Neither automatically reproduces process scheduling, a remote service's internal state, or effects that bypassed the recorded boundary.

The practical success criterion is shorter time from “something broke” to a reproducible failing test. Measure that workflow, including the remaining manual steps.

See [interfaces](interfaces.md) and [testing](testing.md).
