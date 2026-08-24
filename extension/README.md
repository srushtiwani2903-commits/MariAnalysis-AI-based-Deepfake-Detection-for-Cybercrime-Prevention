# DeepGuard Browser Extension (Prototype)

Right-click any image in Chrome/Edge to check it for AI-generated / deepfake
content using the MariAnalysis backend.

## Features
- Context menu: right-click an image -> **DeepGuard: check image for AI / deepfake**
- System notification with verdict, fake %, trust score and risk
- Inline badge drawn over scanned images on the page
- Popup: save your API key + paste an image URL for a quick check

## Setup
1. Start the backend (`python run.py` in `backend/`).
2. Create an API key: log in to the web app -> Profile -> create an API key
   (keys are shown exactly once, prefixed `ma_`).
3. Load the extension:
   - Chrome: `chrome://extensions` -> enable **Developer mode** -> **Load unpacked** -> select this folder.
   - Edge: `edge://extensions` -> enable **Developer mode** -> **Load unpacked**.
4. Open the popup and paste your API key, then save.

## Usage
- Right-click any image on a page -> **DeepGuard: check image for AI / deepfake**.
- Or open the popup, paste an image URL and click **Analyze Image**.

## Notes
- The extension talks to `http://localhost:5001/api/extend/analyze`.
  To point it at another host, edit `API_URL` in `background.js` and `popup.js`
  and add the host to `host_permissions` in `manifest.json`.
- API keys are stored locally in `chrome.storage.local` and never leave the device.
- This is a prototype: the verdicts come from the same deterministic heuristic
  engines as the web app and are forensic guidance, not proof.
