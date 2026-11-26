# Nearby Services: new foundation

This is a **development prototype**, rebuilt separately from the earlier Nearby Services app. The earlier prototype is untouched. The Expo app targets web, Android and iOS, backed by a Django API.

## What this stage includes

- Customer and provider accounts; phone verification through eSMS and provider identity verification through Didit, once configured.
- Administrator-managed categories: add, rename, enable and disable them without an app update. The initial categories include Barbering & Shaving and House Managers.
- Providers can offer multiple categories, with either a fixed price or a quote. Each category needs a separate manual qualification approval.
- Customers can search approved providers within 20 km, request a date and time, and accept a quote. Fixed prices are accepted at request time and checked again by the server.
- Providers accept a fixed-price request or offer a quote, mark work complete, and customers confirm completion or raise a dispute. Disputes appear in the administrator's booking list. Confirmation sets the booking to **payment due**, not paid.

## Not built yet

M-Pesa collection and payouts, the 5% commission, transaction fees, dispute resolution actions, chat, reviews, notifications and administrator-created provider accounts are later stages. No actual payment is collected. Do not use this prototype for real bookings. Accounts, bookings and categories from the previous prototype are not imported.

## Run locally

The database has already been migrated and dependencies installed on this machine. Start the backend:

```powershell
cd "C:\Users\emman\Documents\School Project\nearby-services-v2\backend"
.\.venv\Scripts\python.exe manage.py runserver
```

In another terminal:

```powershell
cd "C:\Users\emman\Documents\School Project\nearby-services-v2\mobile"
npm.cmd run web
```

For Android or iOS, run `npm.cmd start` and open with Expo Go. A phone cannot reach `127.0.0.1` on your computer: in the mobile terminal set `EXPO_PUBLIC_API_URL` to `http://YOUR_COMPUTER_LAN_IP:8000/api`, add that IP to `DJANGO_ALLOWED_HOSTS` in the backend terminal, and run Django with `runserver 0.0.0.0:8000`. Only do this on a trusted development network. Browser location requires a secure context, such as localhost or HTTPS.

To set up another machine, create a Python virtual environment, install `backend\requirements.txt`, run `manage.py migrate`, and run `npm.cmd install` inside `mobile`.

## Categories and reviews

Create an admin account with `.\.venv\Scripts\python.exe manage.py createsuperuser`, then sign in at `http://127.0.0.1:8000/admin/`. Use **Categories** to manage service types and **Offerings** to approve each provider's profession after checking relevant qualifications and licences through a suitable secure process. The prototype does not collect qualification documents. Search requires the category and offering to be active, a location, approved profession, verified phone and approved identity.

## Verification setup

Obtain credentials yourself. Never place keys in the mobile app, source control or chat. Before starting Django, set these in the backend terminal:

```powershell
$env:ESMS_API_KEY = "<your eSMS Verify API key>"
$env:ESMS_VERIFY_APP_ID = "<your Verify app ID>"
$env:DIDIT_API_KEY = "<your Didit API key>"
$env:DIDIT_WORKFLOW_ID = "<your published Didit workflow ID>"
```

Configure an [eSMS Verify app](https://docs.esmsafrica.io/docs/verify) for Kenya. Configure a [Didit workflow](https://docs.didit.me/integration/api-full-flow) with ID document verification, liveness, face matching and Kenya national ID database validation (`ken_national_id`). Identity approval requires all four results and a full Kenyan registry match to the registered first and last names. Providers must press **Refresh identity status** after the hosted flow. If names differ or a check is unavailable, the status remains pending.

Provider accounts and credentials are not included. Live integrations have not been tested; sandbox verification is simulated and must not be used to approve real people. Verification reduces risk but does not guarantee identity, qualifications or safety. Additional safeguarding is especially important for childcare.

## Before launch

This is not production-ready. Obtain Kenyan legal and data-protection advice; establish privacy, consent, retention, deletion and incident procedures; vet providers and safeguarding policies; and validate vendor access, costs and terms. Add secure account recovery, abuse controls, audit logs, production storage, backups, HTTPS, monitoring, secure sessions and independent security review. SQLite, the Django development server and in-memory throttling are only for local development.

## Tests

```powershell
cd "C:\Users\emman\Documents\School Project\nearby-services-v2\backend"
.\.venv\Scripts\python.exe manage.py test marketplace
cd "..\mobile"
npx.cmd tsc --noEmit
npx.cmd expo export --platform web
```
