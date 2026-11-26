# Nearby Services: new foundation

This is a **development prototype**, rebuilt separately from the earlier Nearby Services app. The earlier prototype is untouched. The Expo app targets web, Android and iOS, backed by a Django API.

## What this stage includes

- Customer and provider accounts; phone verification through eSMS and provider identity verification through Didit, once configured.
- Administrator-managed categories: add, rename, enable and disable them without an app update. The initial categories include Barbering & Shaving and House Managers.
- Providers can offer multiple categories, edit their fixed prices or switch to quote pricing. Price changes apply to future bookings only. Each category needs a separate manual qualification approval.
- Customers can search approved providers within 20 km, request a date and time, and accept a quote. Fixed prices are accepted at request time and checked again by the server.
- Once a booking is confirmed, the customer and provider can see and call each other's verified phone numbers. Numbers are not shared for pending, quoted or declined requests.
- Providers mark work complete, and customers confirm completion or raise a dispute. Administrators can resolve disputes from the booking page in Django admin with an outcome and private note. Payment due does not mean paid.
- Customers and providers can exchange text messages on a booking. Customers can leave one 1–5-star review after confirming completion; ratings and comments appear in search and review details.
- Booking, message, review and dispute updates appear in an in-app inbox; messages and inbox require manual refresh.
- Sign-in is restored using device secure storage on Android and iOS, and an HTTP-only server session on supported web deployments.

## Not built yet

Real M-Pesa collection and payouts, transaction fees, push/email notifications and administrator-created provider accounts are later stages. Sandbox checkout does not collect real money or mark bookings as paid. Chat is text-only and notifications are in-app only. Do not use this prototype for real bookings. Accounts, bookings and categories from the previous prototype are not imported.

Administrators resolve disputes from a booking's change page in Django admin. Choose **Payment due** or **Closed without payment** and enter an internal note. Both parties receive an in-app update; no payment is initiated or recorded as paid.

## Privacy and safety

The [privacy policy](./PRIVACY.md) and registration screen disclose the information currently handled by the prototype, including account and phone details, provider locations, booking addresses/details, messages, reviews, verification, and notifications. The policy is a draft: replace the business/contact placeholders and confirm actual retention and vendor terms before public launch. The prototype has no upload feature or public storage bucket, no subscriptions or trials, and no AI assistant. ID documents entered in Didit's hosted flow are handled by Didit, not uploaded to this app. There is no automatic data-retention or deletion process. Booking chat is not monitored for emergencies; the app is not a crisis service.

## M-Pesa sandbox checkout

The app has an optional **sandbox-only** STK Push flow. It uses Safaricom's sandbox endpoint, a temporary KSh 0 additional fee and a 5% test commission. It does not collect real money, initiate B2C payouts, or mark the booking as paid. It accepts whole-shilling prices only. A single test attempt is allowed per booking; an unknown outcome requires investigation rather than an automatic retry.

Safaricom needs a publicly reachable HTTPS backend callback; configure that separately before testing. In the backend terminal only, set the following values from your Daraja sandbox app and simulator. Never share them in chat or commit them:

```powershell
$env:DEBUG = "1"
$env:MPESA_SANDBOX_ENABLED = "1"
$env:MPESA_CONSUMER_KEY = "<sandbox consumer key>"
$env:MPESA_CONSUMER_SECRET = "<sandbox consumer secret>"
$env:MPESA_SHORTCODE = "<sandbox shortcode>"
$env:MPESA_PASSKEY = "<sandbox passkey>"
$env:MPESA_CALLBACK_URL = "https://YOUR_PUBLIC_BACKEND_HOST/api/payments/mpesa/callback/"
```

These settings last only for that terminal session; start `manage.py runserver` in the same terminal. Use only a Safaricom sandbox test number. The callback acknowledges messages but does not trust them to mark a transaction successful; the customer must press **Refresh sandbox status**, which queries Daraja. A timeout or inconclusive result may require checking the sandbox portal; there is no automatic retry or reconciliation. Live integration requires a separate design, approved fees, secure callback handling and thorough testing.

## Run locally

Apply database migrations before starting the backend:

```powershell
cd "C:\Users\emman\Documents\School Project\nearby-services-v2\backend"
$env:DEBUG = "1"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

In another terminal:

```powershell
cd "C:\Users\emman\Documents\School Project\nearby-services-v2\mobile"
npm.cmd run web
```

For Android or iOS, run `npm.cmd start` and open with Expo Go. A phone cannot reach `127.0.0.1` on your computer: in the mobile terminal set `EXPO_PUBLIC_API_URL` to `http://YOUR_COMPUTER_LAN_IP:8000/api`, add that IP to `DJANGO_ALLOWED_HOSTS` in the backend terminal, and run Django with `runserver 0.0.0.0:8000`. Only do this on a trusted development network. Browser location requires a secure context, such as localhost or HTTPS.

To set up another machine, create a Python virtual environment, install `backend\requirements.txt`, set `$env:DEBUG = "1"` in the backend terminal for local development, run `manage.py migrate`, and run `npm.cmd install` inside `mobile`. Run `manage.py migrate` after pulling changes to update an existing database.

### Browser sessions

For local web development, open the app on `localhost` and use the default `http://localhost:8000/api` backend. Do not mix `localhost` and `127.0.0.1`, which browsers treat as different sites. Browser sessions use an HTTP-only cookie and CSRF protection; they expire after Django's default two weeks. Native sign-out revokes the existing shared API token, so it signs out other native devices using that token too.

For a future HTTPS deployment, use frontend and API hostnames on the same site, configure `EXPO_PUBLIC_API_URL` to the HTTPS API, set `DEBUG=0`, provide a strong `DJANGO_SECRET_KEY` from a secret manager, and explicitly set `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `REDIS_URL`, and `SECURE_HSTS_SECONDS`. Non-debug startup requires HTTPS redirect, a positive HSTS duration, and Redis so throttling is shared across workers. Set `TRUST_X_FORWARDED_PROTO=1` only when a trusted reverse proxy terminates TLS and overwrites `X-Forwarded-Proto`; otherwise leave it unset. Use `rediss://` for a remote Redis service. Secure cookies are enabled automatically when `DEBUG=0`. Cross-site deployments may be blocked by browser third-party cookie restrictions. These settings alone do not make the prototype production-ready.

## Categories and reviews

Create an admin account with `.\.venv\Scripts\python.exe manage.py createsuperuser`, then sign in at `http://127.0.0.1:8000/admin/`. Use **Categories** to manage service types and **Offerings** to approve each provider's profession after checking relevant qualifications and licences through a suitable secure process. The prototype does not collect qualification documents. Search requires the category and offering to be active, a location, approved profession, verified phone and approved identity.

To resolve a dispute, filter **Bookings** by **Under review**, open the disputed booking, choose an outcome, enter an internal resolution note and save. Only disputed bookings can be resolved. The booking and its History record the administrator, time and decision. Closing without payment does not issue a refund; payment due does not collect a payment.

## Verification setup

Obtain credentials yourself. Never place keys in the mobile app, source control or chat. Before starting Django, set these in the backend terminal:

```powershell
$env:DEBUG = "1"
$env:ESMS_API_KEY = "<your eSMS Verify API key>"
$env:ESMS_VERIFY_APP_ID = "<your Verify app ID>"
$env:DIDIT_API_KEY = "<your Didit API key>"
$env:DIDIT_WORKFLOW_ID = "<your published Didit workflow ID>"
```

Configure an [eSMS Verify app](https://docs.esmsafrica.io/docs/verify) for Kenya. Configure a [Didit workflow](https://docs.didit.me/integration/api-full-flow) with ID document verification, liveness, face matching and Kenya national ID database validation (`ken_national_id`). Identity approval requires all four results and a full Kenyan registry match to the registered first and last names. Providers must press **Refresh identity status** after the hosted flow. If names differ or a check is unavailable, the status remains pending.

Provider accounts and credentials are not included. Live integrations have not been tested; sandbox verification is simulated and must not be used to approve real people. Verification reduces risk but does not guarantee identity, qualifications or safety. Additional safeguarding is especially important for childcare.

## Before launch

This is not production-ready. Obtain Kenyan legal and data-protection advice; establish privacy, consent, retention, deletion and incident procedures; vet providers and safeguarding policies; and validate vendor access, costs and terms. Add secure account recovery, abuse controls, audit logs, production storage, backups, monitoring, secure sessions and independent security review. SQLite, the Django development server and in-memory cache are only for local development.

## Tests

```powershell
cd "C:\Users\emman\Documents\School Project\nearby-services-v2\backend"
$env:DEBUG = "1"
.\.venv\Scripts\python.exe manage.py test marketplace
cd "..\mobile"
npx.cmd tsc --noEmit
npx.cmd expo export --platform web
```
