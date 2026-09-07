# Facebook Marketplace Feasibility Gate

**Decision date:** 2026-09-07

## Decision

**No-go for a Facebook Marketplace collector.** The official Meta documentation reviewed for this project does not establish a public Graph API or partner feed that authorizes third-party searching and harvesting of consumer Facebook Marketplace listings by query and location. The Marketplace API reference was not available as an extractable public reference during review, and the general Graph API documentation does not grant Marketplace listing-search access by implication.

This repository must not add a Facebook collector until Meta or an authorized partner provides written, current authorization for this exact listing-search use case and the required app review/access approval is complete.

## Findings

- The [Graph API overview](https://developers.facebook.com/docs/graph-api/overview) describes authenticated Graph API access using app, user, and other access tokens. It does not document a general Marketplace search feed.
- The [Graph API rate-limit documentation](https://developers.facebook.com/docs/graph-api/overview/rate-limiting) says all API requests are rate-limited. Platform limits are usage-dependent; the documented application formula is `200 * Number of Users` calls within a rolling hour, subject to throttling and endpoint-specific rules. A collector could not assume a fixed quota.
- Meta requires app/user authorization appropriate to the endpoint. Any required permissions, Advanced Access, or App Review approval must be confirmed for the specific Marketplace use case before implementation.
- Meta's [Commerce Policies](https://www.facebook.com/policies_center/commerce/) apply to Marketplace commerce content. They include restrictions on prohibited and restricted goods and note that non-compliance can result in listing removal or suspension of access.
- Data use must comply with Meta's [Platform Terms](https://developers.facebook.com/terms/dfc_platform_terms/), [Developer Policies](https://developers.facebook.com/devpolicy/), and [Privacy Policy](https://www.facebook.com/about/privacy). The application would need a documented lawful purpose, privacy notice, access controls, minimization, retention schedule, deletion process, and handling for user/app data deletion requests.
- Rate-limit handling would need to stop or back off on throttling, honor usage headers and error responses, spread requests evenly, and avoid overlapping queries. These controls are irrelevant until an authorized endpoint exists.

## Prohibited implementation paths

This project will not use:

- HTML or browser scraping of Marketplace pages
- CAPTCHA or anti-bot bypasses
- stealth fingerprints, proxy rotation, or evasion behavior
- automated credential entry or password/session capture
- private, authenticated, or user-only page access without explicit supported API authorization
- an unofficial endpoint, reverse-engineered client protocol, or copied listing feed

## Approval requirements before reconsideration

A future implementation request must include all of the following:

1. A current Meta or authorized partner API/feed specification naming the Marketplace listing-search endpoint.
2. Written confirmation of the permitted query, location, pagination, listing fields, storage, and commercial use.
3. Required permissions, access level, App Review status, token type, and token lifecycle.
4. Endpoint-specific rate limits, throttling signals, retry rules, and quota-monitoring requirements.
5. Data-use, privacy, retention, deletion, and user-rights requirements reviewed by the project owner.
6. A test fixture or sandbox response format that can be used without live Marketplace access.

## Alternative

Until those requirements are met, use an existing authorized/public marketplace integration such as the current Craigslist collector, or add another marketplace only when its published API or feed terms permit the intended search and storage behavior. Prompt 8 remains blocked and no `collectors/facebook.py` should be created from this decision.
