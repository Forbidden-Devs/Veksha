"""Public privacy policy for the Veksha browser extension."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
@router.get("/privacy/", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Veksha Privacy Policy</title>
  <style>
    :root { color-scheme: light dark; }
    body { font: 16px/1.6 system-ui, sans-serif; margin: 0; }
    main { max-width: 760px; margin: 0 auto; padding: 48px 24px 72px; }
    h1, h2 { line-height: 1.2; }
    h2 { margin-top: 2rem; }
    .updated { color: #666; }
    @media (prefers-color-scheme: dark) { .updated { color: #aaa; } }
  </style>
</head>
<body>
<main>
  <h1>Veksha Privacy Policy</h1>
  <p class="updated">Effective date: July 13, 2026</p>

  <p>Veksha processes information only to provide the language-learning
  features requested by the user. This policy applies to the Veksha browser
  extension and the Veksha service used by the extension.</p>

  <h2>Information processed</h2>
  <p>Depending on the features the user chooses, Veksha may process:</p>
  <ul>
    <li>a display name and internal account identifier;</li>
    <li>authentication tokens and, for optional Google sign-in, the Google
      profile name and email address returned by Google;</li>
    <li>selected text, page text, subtitle text, OCR results, and the domain
      of the current website;</li>
    <li>chat messages, saved vocabulary, training answers, learning history,
      language preferences, goals, settings, and feature state;</li>
    <li>an optional linked Telegram account identifier and subscription
      status when Telegram billing is used.</li>
  </ul>

  <h2>How information is used</h2>
  <p>Information is used to provide translations, explanations, language
  analysis, vocabulary storage and synchronization, personalized training,
  lessons, chat, authentication, optional reminders, support, and optional
  subscription billing. Veksha does not sell personal data and does not use
  personal data for advertising, credit decisions, or purposes unrelated to
  the extension's language-learning features.</p>

  <h2>Information sharing and service providers</h2>
  <p>The extension sends the information required for a requested feature to
  the Veksha production service. Text submitted for translation, explanation,
  chat, grammar, immersion, lesson, subtitle, OCR-related, or training
  features may be processed by OpenAI's API to generate the requested result.
  Railway hosts the Veksha production service. Optional Google authentication
  is processed by Google. Optional subscription billing is processed through
  Telegram. These providers receive only the information needed to perform
  their respective services.</p>

  <h2>Browser permissions and local storage</h2>
  <p>Veksha accesses page content only to provide features the user enables or
  invokes, such as selection translation, immersion, grammar analysis,
  subtitle tools, vocabulary frequency, reminders, and OCR. The extension
  stores an authentication token, account identifier, preferences, and
  feature state in local browser extension storage so it can work across
  sessions. OCR JavaScript, WebAssembly, and language assets are packaged
  locally with the extension; Veksha does not download or execute remote code.</p>

  <h2>Retention and security</h2>
  <p>Local extension data remains in the browser until the user clears the
  extension's data or uninstalls it. Server-side account and learning data is
  retained while needed to operate the account and provide requested
  features. Veksha uses HTTPS for data transmitted between the extension and
  the production service and limits access to account data using bearer-token
  authentication.</p>

  <h2>User choices</h2>
  <p>Google sign-in and Telegram linking are optional. Users can disable
  optional page-analysis and reminder features in the extension settings,
  clear local extension data through the browser, unlink optional services,
  and stop using the service at any time. Requests concerning account data or
  deletion can be submitted through the developer contact shown on Veksha's
  Chrome Web Store or Firefox Add-ons listing.</p>

  <h2>Policy changes</h2>
  <p>This policy may be updated when Veksha's features or data practices
  change. The effective date at the top of this page identifies the current
  version.</p>
</main>
</body>
</html>"""
