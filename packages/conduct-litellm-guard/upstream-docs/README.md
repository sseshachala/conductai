# Upstream docs — held for submission after BerriAI/litellm#38143 merges

Contents of this directory are drafted for submission to
[`BerriAI/litellm-docs`](https://github.com/BerriAI/litellm-docs)
as a follow-up PR once
[BerriAI/litellm#38143](https://github.com/BerriAI/litellm/pull/38143)
merges.

## Files

- `conduct.md` — the guardrails docs page. Destination:
  `docs/proxy/guardrails/conduct.md` in `BerriAI/litellm-docs`.
  Follows the Aporia page pattern (Docusaurus MDX with `Tabs` /
  `TabItem` imports).

## Post-merge submission checklist

- [ ] Fork `BerriAI/litellm-docs`.
- [ ] Copy `conduct.md` to `docs/proxy/guardrails/conduct.md`.
- [ ] Update `sidebars.js` to add the Conduct entry alongside Aporia /
      Lakera in the guardrails section.
- [ ] Open PR titled `docs: add Conduct guardrail page`, CC
      `@Yucheng He`.
