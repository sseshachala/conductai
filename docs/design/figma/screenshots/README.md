# Real product screenshots (capture inventory)

This directory holds real product screenshots that replace the drawn in-product panels
in `../exports/*.png`. See the Screenshot inventory table in
[`../../figma-five-page-handoff.md`](../../figma-five-page-handoff.md).

## Capture rules

- Seeded demo workspace only. No customer data. No real emails, tokens, or account IDs.
- 1440×900 desktop and 375×812 mobile, PNG.
- Redact secrets, real user IDs (except demo `lens:user_*`), and third-party tokens.

## Filenames

Match the mockup panels the capture replaces, e.g.:

- `home-hero-lens-confirm.png`
- `home-run-summary.png`
- `guard-activity-row.png`
- `guard-policy-yaml.png`
- `guard-slack-approval.png`
- `registry-pack-grid.png`
- `evidence-receipt-block.png`
- `evidence-lens-transcript.png`
- `mcp-tool-trace.png`

MCP hero is an SVG diagram — save as `mcp-hero-diagram.svg`, not a screenshot.
