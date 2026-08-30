# Facebook media file-dialog hotfix

## Symptom

During an automated Facebook media post, clicking the visible Photo/Video control could open the Windows native file picker. The picker commonly opened at the user's Desktop (Windows' remembered/default location), not at Social Publisher's asset directory. Once the native dialog owned focus, later Selenium DOM actions could fail with `ElementNotInteractableException`.

## Asset source of truth

Social Publisher assets remain stored under the runtime `data/uploads/` directory. Publish jobs resolve the immutable `stored_name` through `get_media_path()` and pass the resulting absolute path to the platform adapter.

The Windows file picker is not part of the intended publishing workflow and must not be used to choose project assets.

## Fix

- Facebook Photo/Video activation now uses an untrusted DOM mouse event sequence rather than a trusted WebDriver/ActionChains click.
- The real project file is still assigned directly to Facebook's `input[type=file]` using Selenium `send_keys(absolute_path)`.
- Ordinary Facebook controls now contain `ElementNotInteractableException` and perform bounded interaction retries.
- Composer text focus uses the guarded click primitive as well.
- Raw ChromeDriver interactability stack traces should no longer be the normal user-facing failure message for these paths.

## Expected live behavior

1. Start a Facebook image post using an asset already stored in Social Publisher.
2. Facebook Composer opens.
3. Photo/Video mode activates.
4. **No Windows Explorer/file picker appears.**
5. The selected asset is attached automatically from `data/uploads/`.
6. The flow continues to Next/Post and verification.
