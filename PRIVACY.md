# Privacy policy

**Effective date:** 26 November 2026
**Status:** Prototype draft. Replace every bracketed placeholder and have this policy reviewed before public launch.

## Who operates this service

This Nearby Services prototype is operated by **[business or data controller name]**. For privacy questions or requests, contact **[privacy contact email]**.

## Information the app handles

Depending on how you use the app, it may handle:

- Account details: username, first and last name, phone number, and a password that Django stores as a password hash.
- Provider profile details: service description, service location coordinates, phone-verification status, and identity-verification status and session reference.
- Booking details: customer and provider account references, service address, job description, requested date and time, agreed price, booking status, and any administrator dispute-resolution note.
- Booking communications: text messages between the customer and provider, and in-app notification content and read status.
- Reviews: a 1–5-star rating and optional comment. Reviews are displayed publicly on service listings without the reviewer's name.
- Nearby-search coordinates: a customer's current coordinates are sent to the API to find nearby services. The search coordinates are not saved to the customer's profile by this search.
- Technical session information: browser session and CSRF cookies on web, or an authentication token stored in secure device storage on native apps.

Provider service coordinates are stored in the provider profile. Customer nearby-search coordinates are sent to the API for that search and are not written to the customer's profile; server or hosting logs may retain request metadata depending on deployment. Booking participants can see each other's names and booking details. A customer's verified phone number is shared with the provider, and the provider's verified phone number with the customer, only after a booking is confirmed.

## Why information is used

Information is used to create and secure accounts, verify phone numbers and provider identity, maintain provider listings, search nearby services, manage bookings and disputes, enable booking messages, show reviews, and deliver in-app notifications.

## Service providers and sharing

- Phone verification is integrated with eSMS Africa. Provider identity verification uses a hosted Didit flow that receives the provider's name and identity documents directly. Information submitted to those services is subject to their own privacy notices and retention practices.
- If the optional M-Pesa sandbox is enabled, the sandbox phone number and test transaction details are sent to Safaricom's sandbox service. This prototype does not collect real payments.
- Booking messages are available to the customer and provider on that booking. Verified phone numbers become visible to both parties after confirmation.
- Review ratings and comments are public on service listings. Do not include private or sensitive information in a review.
- The prototype has no advertising trackers, file-upload feature, or public object-storage bucket configured. The app itself does not receive identity-document uploads; documents entered in Didit's hosted verification flow are handled by Didit.
- Operators with access to the application server or its database may be able to access stored information to operate or maintain the service.

## Storage and security

The development prototype uses a local SQLite database. A future deployment may use different hosting or storage; this policy must be updated before that happens. Native authentication tokens are stored with Expo SecureStore. Web authentication uses an HTTP-only session cookie and CSRF protection. No system can guarantee perfect security; do not use this prototype for real bookings or sensitive documents.

## Retention and deletion

The prototype has no automatic retention schedule, self-service account deletion, or automated upload deletion. Account, booking, message, review, and notification data remain in the database until an operator removes them. To request access, correction, or deletion, contact **[privacy contact email]**. Requests may require manual handling, and any legal retention requirements must be assessed by the operator. Retention by eSMS Africa, Didit, or Safaricom is governed by those providers' own policies.

## Subscriptions, trials, and testimonials

The app does not currently offer subscriptions or free trials, so it has no subscription cancellation flow or trial-reminder messages. It does not include seeded marketing testimonials. Public reviews are submitted by customers only after they confirm a booking is complete.

## Messages and emergencies

Booking chat is peer-to-peer text messaging, not an AI assistant, crisis service, or monitored emergency channel. If you or someone else is in immediate danger, contact local emergency services or a trusted person.

## Your choices and questions

You can choose whether to provide optional provider profile details and review comments. Some account, verification, and booking information is necessary to use the corresponding features. For privacy requests or questions, contact **[privacy contact email]**.

This draft describes the current prototype, not a guarantee of legal compliance. The operator should confirm the actual deployment, vendors, retention periods, lawful basis, user rights, and contact details with qualified privacy counsel before launch.