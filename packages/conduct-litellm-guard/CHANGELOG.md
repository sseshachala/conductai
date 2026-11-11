# Changelog

## [Unreleased]

### Added
- `async_post_call_success_hook` surfaces Conduct Gateway tool-call correlation
  IDs (#2168): reads `X-Conduct-Tool-Correlation-Ids` from the response, logs a
  `correlation_id` per tool call, and stores the mapping in
  `data["metadata"]["conduct_tool_correlation_ids"]`.
