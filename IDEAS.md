# MariAnalysis — Future Add-ons / Ideas

Roadmap of features to make the website unique vs. other deepfake detectors.
Priorities: the "Top 5" set below is the recommended combination.

## Top 5 (highest impact)

1. **Browser Extension** (Chrome/Firefox)
   - Right-click on any image/video -> "Verify with MariAnalysis".
   - No competitor offers this. Calls the existing `/api/detect/*` endpoints.

2. **WhatsApp / Telegram Bot**
   - Users forward a suspicious image/video and get a verdict in chat.
   - Ideal for the cybercrime-prevention audience; wraps existing detector APIs.

3. **Live Webcam Liveness Test**
   - Real-time "Is the person on this call real?" check from the camera.
   - Uses blink/motion/temporal analysis — the heuristic engine can do it CPU-only.

4. **Digital Fingerprint Vault (Blockchain-lite)**
   - Every scan gets a SHA-256 hash + timestamp recorded on a public ledger.
   - Creators can register original media as proof of authenticity.
   - Implementation is simple: a hash + timestamp endpoint.

5. **Forensic Heatmap Explorer**
   - Interactive overlay on the results page showing exactly which
     pixels/frames/frequencies were manipulated.
   - Turns XAI text into visual storytelling.

## Extra polish ideas

6. **Community Voting** — multiple users verify a media file; reputation-weighted verdicts.
7. **Live Deepfake Threat Feed** — trending/famous deepfake campaign alerts (scraped feeds + admin posts).
8. **PWA + offline mode** — installable app feel.
9. **Scan Sharing Cards** — verdict rendered as a shareable social card (OG image).
10. **Creator Monitoring Dashboard** — celebrities/creators get alerts about deepfakes of their own face.

## Recommended combination

Browser extension + WhatsApp/Telegram bot + Live Liveness Test + Fingerprint Vault.
These four are things no competitor currently offers.
