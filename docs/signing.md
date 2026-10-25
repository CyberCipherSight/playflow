# Local upload-key signing

PlayFlow can generate an upload key and sign an already-built release AAB without starting Gradle. This is useful when Android Studio can build the app but the agent's execution environment blocks Gradle's local process communication.

An APK is not an AAB. Running `assembleDebug` produces a debug APK that is already debug-signed; it is not a release bundle. Build an unsigned release bundle with `:app:bundleRelease` before using `sign-bundle`. Android documents [separate bundle signing with jarsigner](https://developer.android.com/build/building-cmdline#sign_bundle); `apksigner` is for APKs.

## Generate a key once

```bash
playflow signing-init
```

The encrypted key and certificate are created under the configured state directory's `signing/` folder (normally `.playflow/signing/`). By default, the password goes directly into a unique persistent folder under `~/.config/playflow/signing/<app>/generations/`. The key is RSA 3072-bit in a PKCS12 keystore, alias `upload`, valid for 10,950 days. A strong password is generated, saved locally, and never displayed or put in command arguments. The JSON descriptor records paths and a public certificate fingerprint, without password values. Existing signing files are never overwritten; this command does not replace a registered upload key.

The password file requires a filesystem enforcing private file permissions on POSIX. To choose another persistent private location:

```bash
playflow signing-init \
  --password-file "$HOME/.config/playflow/signing/my-app/upload-password.txt"
```

Back up the key and password before using this signing identity. Do not use `/tmp` for signing credentials: it may disappear on restart. A generated upload key has no remote effect until used/registered for a Play upload.

## Build, back up and sign from a normal terminal

```bash
playflow finish-release
```

This command verifies the signing password and certificate, saves a complete backup in a unique generation under `~/.config/playflow/signing/<app>/`, adds signing ignore rules to the Android project, and copies the encrypted key there. It runs the configured Gradle task, locates the module's bundle, signs a separate copy, and updates the private manifest's `build.aab_path`. It never uploads or publishes. Run it from your normal terminal when the agent environment cannot write persistent credentials or run Gradle. Gradle should produce an unsigned bundle; already signed bundles are deliberately rejected.

Use `playflow finish-release --open-console` to request a Firefox tab at the configured `browser.console_url` after successful signing. If you already have a signed bundle, `playflow open-console` opens it without rebuilding. Configure the existing Firefox profile first; launching does not fill questionnaires or verify the page. A failed browser launch leaves the successfully signed bundle and manifest intact.

If an older setup lost its temporary password, the command checks the app's persistent password backups and verifies each candidate against the original certificate. Without a matching password it stops, preserving the existing key. The encrypted keystore cannot supply a forgotten password.

Only when that key has **never been uploaded or registered with Google Play**, use:

```bash
playflow finish-release --recover-unused-key
```

This explicitly permits creating a replacement when no password works. The replacement key and password are created and verified in persistent storage before the old local signing directory moves into `signing-archive/`. Existing backups are retained. If the original key is already registered, restore its password or follow Google's upload-key recovery process; this option cannot preserve that identity. Keep an independent backup of the persistent credentials as well.

After confirming that Play accepted an upload signed with this certificate, record that fact locally:

```bash
playflow signing-record-upload 'AA:BB:...:FF'
```

Supply the full upload-certificate SHA-256 fingerprint. This verifies the active local key, writes a registration marker in the persistent backup directory, and marks its descriptor. It does not query Google or upload a file. A recorded registered key cannot be replaced with `--recover-unused-key`, even if an older descriptor is later restored. Matching password backups can still restore the same key. For uploads made outside PlayFlow, record the confirmed registration before attempting any recovery.

## Sign an AAB

```bash
playflow sign-bundle \
  --aab /path/to/app-release.aab \
  --output /path/to/app-release-signed.aab
```

With `--aab` omitted, the configured module/artifact path is used. The default output is the configured state directory's `artifacts/app-release-signed.aab`.

The signer checks the archive's basic AAB layout, duplicate/corrupt entries, and pre-existing signing metadata. It refuses APKs and already-signed bundles, verifies the saved upload certificate fingerprint, signs a new copy with SHA-256/RSA, then runs strict verification against the same upload keystore. Unsigned entries added after signing fail verification. The source and existing output bundles are never overwritten.

This verifies JAR signatures. It does not parse the protobuf manifest, prove a release variant, run bundletool, verify runtime behavior, or certify Play acceptance. With `sign-bundle`, select the signed output explicitly in `build.aab_path` before publishing. The separate `finish-release` command updates that field after successful signing. Neither command uploads anything.

Passwords are passed to JDK tools through file references, not literal command-line values, following [keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html) and [jarsigner](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html) support. State stores signing paths, certificate fingerprints and bundle hashes, not password contents.

Signing directories and key/password filename patterns are ignored and excluded from distributions. These rules reduce accidental sharing; manually review repository contents and backups before publishing. New local signing files do not replace the need to configure Play App Signing for a first release.
