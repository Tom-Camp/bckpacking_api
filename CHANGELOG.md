## v0.2.0 (2026-10-31)

### Feat

- **backup.sh**: adding backup script and example env
- **auth**: refuse login until the email address is verified
- **auth**: verify email addresses with an emailed link
- **auth**: revoke access tokens after a password reset or change
- **auth**: reset forgotten passwords by email through Resend
- **user**: add endpoint for a signed-in user to change their password
- **scripts**: add a development seed script
- **GearCategoryOption**: adding category endpoint
- **Share**: adding sharing
- **gear**: add user gear closet with trip gear links and copy-from-trip
- **users**: add picture and body_weight_g to User
- **api.v1.trips**: adding Trips routes
- **TripNote**: adding notes to Trip model
- **Trip**: adding Trip model
- **all**: initial commit

### Fix

- **config**: updating default email to use the reset.bckpack.ing address
- **logging**: make LOG_LEVEL filter uvicorn's propagated records
- **config**: URL-encode the Postgres user and password in database_url
- **migrations**: escape % in the database URL and stop defaulting JSON_LOGS off
- **logging**: render JSON logs once and keep tracebacks
- **docker**: bind to loopback by default and address review findings
- **trips**: bound int fields to INT32_MAX so oversized values return 422
- **auth**: run bcrypt in a worker thread
- **auth**: run bcrypt in a worker thread
- **schema**: reject blank trip, gear, food and note names
- **trips**: reject map links that aren't http(s) URLs
- **types**: satisfy mypy with sqlmodel 0.0.47 typed constructors
- **admin**: stop admins suspending or re-roling themselves; test auth and admin
- **trips**: return 404, not 403, for another user's trip
- **users**: remove the unauthenticated GET /users routes
- **auth**: normalize emails so case variants can't register twice or claim ADMIN_EMAIL
- **Trip**: fixing share token race condition
- **Trip**: adding per section share
- **Gear**: clean up and fortifying Gear.category
- **migrations**: restore accidentally deleted env.py
- **Trip**: minor changes and updates
- **Trip**: store distance and elevation as float in meters
- **Trip**: updating date fields and adding checks
- **api**: let PATCH clear nullable fields and reject null on required fields
- **schemas**: add gear_name to gear create/update/read schemas
- **Trip**: adding gear_name field to Gear model
- **migrations**: migration fix for enum

### Refactor

- **Trip**: changing share token to header
- **api.v1.gear.list_gear_categories**: adding require_active_user dependency
- **Prek**: moving to Prek
- **Gear**: changing category to StrEnum
- **Trip**: changing checklist values from true/false to todo, done, and not_applicable
- **Trip**: moving unit type to User and changing field values to g, m, kcal, etc
- **models**: store enum columns as VARCHAR instead of native Postgres enums
- **routes**: moving admin routes out of user routes
- **Trip**: moving permit_required to checklist
