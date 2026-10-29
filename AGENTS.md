# astock maintenance

- Preserve the upstream history, Apache-2.0 license and attribution.
- Keep the source library independent of its consumers. Do not import a consumer's
  warehouse, policies, credentials, deployment paths or strategy code.
- Put new production code in `src/astock`; support Python 3.10 and newer.
- Keep source identity, raw bytes/hash, request identity and acquisition time.
  A source date is not automatically its publication or historical knowledge time.
- Distinguish a valid empty response from a failed request or invalid schema.
  Never silently substitute another vendor or change units.
- Do not commit credentials, real market payloads, databases or run artifacts.
- Run `make check` for the maintained library. `make check-upstream` separately
  exercises the retained upstream examples; report unavailable dependencies/skips.
