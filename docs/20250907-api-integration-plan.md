### Plan for Integrating App Store Connect API

**1. Update Dependencies:**
- Add `appstoreconnect` to `requirements.txt` to handle App Store Connect API authentication and requests.

**2. Enhance Configuration:**
- The `deploy.yml` workflow already sets up secrets as environment variables. The following App Store Connect API credentials will be added to this configuration:
    - `KEY_ID`
    - `ISSUER_ID`
    - `APPSTORE_PRIVATE_KEY`
- `main.py` will be modified to read these new environment variables.

**3. Implement API Integration:**
- **Create a new function `get_app_details(app_id)`:** This function will initialize the `appstoreconnect` client using the new credentials and fetch the app's name and icon URL using the `app_id` from the webhook.
- **Update `webhook_handler`:**
    - It will extract the `app_id` from the webhook payload (`data.relationships.app.data.id`).
    - It will call `get_app_details()` to retrieve the app's information.
- **Update `parse_apple_notification`:**
    - This function will be modified to accept the app name and icon URL as arguments.
    - It will then use this information to create a richer notification title.
- **Update `format_lark_card`:**
    - This function will be enhanced to include the app's icon in the Lark notification card, making the notifications more informative and visually appealing.

This plan will create a robust integration that automatically enriches webhook notifications with valuable app details.
