# Context regarding Smartsheet SDK native oauth handling
# Please ignore this I say otherwise

You want to know whether the installed Smartsheet SDK already provides token validation or token refresh helpers, so I’m searching the local package sources first and then I’ll summarize what is built in versus what your app must do itself.

I searched the installed SDK in the workspace .venv, and the answer is:

1. There is a prebuilt refresh method.
2. There is not a dedicated “is this access token valid?” helper.

The refresh support is implemented in token.py. The SDK provides Token.refresh_access_token, which takes:
- client_id
- refresh_token
- _hash
- optional redirect_uri

The same module also provides Token.get_access_token in token.py and Token.revoke_access_token in token.py.

That Token API is exposed off the Smartsheet client through dynamic attribute loading in smartsheet.py, so the intended call shape is effectively:
- client.Token.refresh_access_token(...)
- client.Token.get_access_token(...)

Important detail: the SDK refresh method does not take the raw client secret. It expects the OAuth hash described in the docstring in token.py, specifically the SHA-256 hash of:
- app_secret + "|" + refresh_token

For validation, I did not find any dedicated helper like “validate_token”, “is_token_valid”, or similar anywhere in the SDK. The practical validation pattern is just making an authenticated API call, typically Users.get_current_user in users.py. If the token is invalid and you have exceptions enabled, the SDK raises ApiError or HttpError from exceptions.py.

So the direct answer is:

- Validates access token: No dedicated prebuilt method. Use a simple authenticated call such as client.Users.get_current_user().
- Refreshes access token: Yes. Use client.Token.refresh_access_token(...), but it requires the Smartsheet OAuth hash, not the plain client secret.

One more implication for your app: the SDK does not appear to automatically refresh expired tokens for you. You still need to decide when to call refresh_access_token and then rebuild or update the client with the new access token.

My question: Should we change the oauth_handler implementation to follow what the sdk expects?

Not necessarily. Here's my assessment:

**Arguments FOR using SDK's Token API:**
1. Consistency — use the same SDK for all API operations, not mix with raw `requests`
2. Future-proofing — if Smartsheet SDK changes, you get those fixes automatically
3. Leverage SDK error handling and retry logic
4. Cleaner architecture

**Arguments AGAINST:**
1. **Hash requirement** — SDK's `refresh_access_token()` requires a SHA-256 hash of `app_secret + "|" + refresh_token`, not the plain secret. This adds complexity.
2. **Client instance overhead** — you'd need to create a temporary Smartsheet client just to call the Token refresh method, which feels circular (you need a token to refresh a token).
3. **Current approach already works** — your manual `refresh_tokens()` using `requests.post()` is straightforward and reliable.

**My recommendation:**

Keep your current manual `refresh_tokens()` implementation as-is. The real issues to fix are:

1. **Validation** — use `client.Users.get_current_user()` (which your code already does), but fix the exception status code extraction in `validate_client()` to properly detect 401/403 from the SDK exception structure.

2. **Runtime refresh** — add a retry-on-401 wrapper in the repository layer so that when API calls fail with 401 mid-execution, they trigger refresh and retry automatically.

The manual token refresh approach is fine because:
- It's already working (you have valid tokens in your token files)
- It's explicit and easy to understand
- You don't need the SDK's complexity (the hash) or overhead (temporary client instance)
- You're not tied to how the SDK exposes the Token API

**Bottom line:** Fix the validation bug and add runtime refresh logic to the repository. Leave oauth_handler's refresh_tokens() as-is. The current design where oauth_handler manages tokens independently from the API client is actually clean separation of concerns.

Does that align with what you were thinking?