"""Public product and legal pages required by extension stores and OAuth."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_STYLE = """
    :root { color-scheme: light dark; --accent: #c95325; }
    * { box-sizing: border-box; }
    body { font: 16px/1.6 system-ui, sans-serif; margin: 0; }
    main { max-width: 800px; margin: 0 auto; padding: 48px 24px 72px; }
    h1, h2 { line-height: 1.2; }
    h2 { margin-top: 2rem; }
    a { color: var(--accent); }
    nav { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 2rem; }
    .brand { display: flex; align-items: center; gap: 1rem; }
    .mark { display: grid; place-items: center; width: 64px; height: 64px;
      border-radius: 18px; color: white; background: var(--accent);
      font-size: 1.8rem; font-weight: 700; }
    .lead { font-size: 1.2rem; }
    .updated, footer { color: #666; }
    footer { border-top: 1px solid #8885; margin-top: 3rem; padding-top: 1rem; }
    @media (prefers-color-scheme: dark) { .updated, footer { color: #aaa; } }
"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def homepage() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Veksha is a browser extension for contextual language learning.">
  <title>Veksha — learn languages from the web</title>
  <style>{_STYLE}</style>
</head>
<body>
<main>
  <div class="brand"><div class="mark" aria-hidden="true">Ve</div><h1>Veksha</h1></div>
  <p class="lead">Veksha is a browser extension that turns webpages, video
  subtitles, and selected text into contextual language-learning material.</p>
  <p>Translate selections, save useful vocabulary, practise with spaced
  repetition, explore explanations, and continue with the same learning
  profile across supported browsers and devices.</p>
  <p>Google sign-in is used only for optional account authentication and
  synchronization. Veksha requests basic profile information: name and email.</p>
  <nav aria-label="Legal and support links">
    <a href="/privacy">Privacy Policy</a>
    <a href="/terms">Terms of Service</a>
    <a href="mailto:danfromomsk@gmail.com">Support</a>
  </nav>
  <footer>© 2026 Veksha</footer>
</main>
</body>
</html>"""


@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
@router.get("/privacy/", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Veksha Privacy Policy</title>
  <style>{_STYLE}</style>
</head>
<body>
<main>
  <h1>Veksha Privacy Policy</h1>
  <p class="updated">Effective date: August 1, 2026</p>

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
      of the current website, and an image crop when the user explicitly
      invokes area translation;</li>
    <li>chat messages, saved vocabulary, training answers, learning history,
      language preferences, goals, settings, and feature state;</li>
    <li>AI feature usage records, including the feature, model, timestamp, and
      provider-reported input, output, cached, reasoning, and total token counts;</li>
    <li>an optional linked Telegram account identifier and subscription
      status when Telegram billing is used.</li>
  </ul>

  <h2>How information is used</h2>
  <p>Information is used to provide translations, explanations, language
  analysis, vocabulary storage and synchronization, personalized training,
  lessons, chat, authentication, optional reminders, support, and optional
  subscription billing. AI usage counts are used for service operations,
  capacity planning, and cost monitoring. Veksha does not sell personal data and does not use
  personal data for advertising, credit decisions, or purposes unrelated to
  the extension's language-learning features.</p>

  <h2>Information sharing and service providers</h2>
  <p>The extension sends the information required for a requested feature to
  the Veksha production service. Text submitted for translation, explanation,
  chat, grammar, immersion, lesson, subtitle, OCR-related, or training
  features may be processed by OpenAI's API to generate the requested result.
  User-selected image crops may first be processed by Google Cloud Vision for
  text recognition; OpenAI vision is used when primary OCR is unavailable.
  An infrastructure hosting provider processes the service's runtime and
  stored account data. Optional Google authentication is processed by Google.
  Optional subscription billing is processed through Telegram. These
  providers receive only the information needed to perform their respective
  services.</p>

  <h2>Browser permissions and local storage</h2>
  <p>Veksha accesses page content only to provide features the user enables or
  invokes, such as selection translation, immersion, grammar analysis,
  subtitle tools, vocabulary frequency, reminders, and OCR. The extension
  stores an authentication token, account identifier, preferences, and
  feature state in local browser extension storage so it can work across
  sessions. Area captures are kept temporarily in extension session memory, consumed
  once by the capture workspace, and are not written to browser storage.</p>

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
  deletion can be sent to <a href="mailto:danfromomsk@gmail.com">danfromomsk@gmail.com</a>.</p>

  <h2>Policy changes</h2>
  <p>This policy may be updated when Veksha's features or data practices
  change. The effective date at the top of this page identifies the current
  version.</p>
  <nav><a href="/">Home</a><a href="/terms">Terms of Service</a></nav>
</main>
</body>
</html>"""


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
@router.get("/terms/", response_class=HTMLResponse, include_in_schema=False)
async def terms_of_service() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Veksha Terms of Service</title>
  <style>{_STYLE}</style>
</head>
<body>
<main>
  <h1>Veksha Terms of Service</h1>
  <p class="updated">Effective date: August 1, 2026</p>

  <p>These Terms govern use of the Veksha browser extension and the Veksha
  online services used by the extension. By using Veksha, you agree to these
  Terms.</p>

  <h2>The service</h2>
  <p>Veksha provides language-learning tools including translation,
  explanations, vocabulary storage, training, lessons, page and subtitle
  analysis, reminders, account synchronization, and related features. Some
  features may be experimental, changed, limited, or discontinued.</p>

  <h2>Accounts</h2>
  <p>You are responsible for access to your browser profile and linked Google
  or Telegram accounts. You must not attempt to access another user's Veksha
  profile. Google sign-in is optional but is required to recover the same
  Veksha profile after local extension data is removed or when moving to
  another browser or device.</p>

  <h2>Acceptable use</h2>
  <p>You may not misuse Veksha, interfere with the service, bypass access or
  subscription controls, probe other accounts, automate abusive traffic,
  upload unlawful content, or use the service in a way that violates law or
  third-party rights. You are responsible for having permission to process
  content you submit.</p>

  <h2>AI-generated information</h2>
  <p>Translations, explanations, exercises, and other generated content may
  contain errors. Veksha is an educational aid and does not provide legal,
  medical, financial, or other professional advice. You should independently
  verify information when accuracy matters.</p>

  <h2>Subscriptions and third-party services</h2>
  <p>Optional paid features may be offered through third-party payment
  services such as Telegram. Their terms may also apply. Google, Telegram,
  OpenAI, infrastructure hosting providers, browser stores, and websites
  viewed through the extension are independent third parties and are governed
  by their own terms.</p>

  <h2>Intellectual property</h2>
  <p>Veksha and its original software, design, and branding are protected by
  applicable intellectual-property laws. These Terms do not transfer
  ownership of Veksha or of third-party content. You retain rights in content
  you submit.</p>

  <h2>Availability and termination</h2>
  <p>The service is provided on an "as is" and "as available" basis without a
  guarantee of uninterrupted operation. Access may be suspended when needed
  for security, abuse prevention, maintenance, legal compliance, or a serious
  violation of these Terms. You may stop using Veksha at any time.</p>

  <h2>Limitation of liability</h2>
  <p>To the extent permitted by law, Veksha's developer is not liable for
  indirect, incidental, special, consequential, or exemplary damages, loss of
  data, or loss resulting from reliance on generated content. Nothing in these
  Terms excludes liability that cannot legally be excluded.</p>

  <h2>Changes and contact</h2>
  <p>These Terms may be updated as the service changes. The effective date
  identifies the current version. Questions can be sent to
  <a href="mailto:danfromomsk@gmail.com">danfromomsk@gmail.com</a>.</p>
  <nav><a href="/">Home</a><a href="/privacy">Privacy Policy</a></nav>
</main>
</body>
</html>"""
