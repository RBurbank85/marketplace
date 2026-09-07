# Dashboard Accessibility Checks

The dashboard has static semantic coverage in `tests/test_api.py`. Run these manual checks for visual and interaction regressions:

- At 320px, 768px, and 1440px wide, confirm headings, queue content, filters, actions, and status text remain visible without page-level horizontal scrolling.
- Use only the keyboard: reach the API key form, refresh, queue filter, each opportunity, and drawer actions; confirm focus is visible, Tab stays inside the open drawer, Escape closes it, and focus returns to the opportunity button.
- Open an opportunity and verify the drawer has a spoken title, loading/error text is understandable, and action outcomes are announced once.
- Check that status words such as `Online`, `Idle`, `Approved`, and `Rejected` remain understandable when color or animation is unavailable.
- Enable `prefers-reduced-motion` and confirm the interface remains usable without required animation.
