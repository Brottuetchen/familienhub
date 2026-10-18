# Releasing

Everything is built by GitHub Actions. Nobody needs Flutter, Xcode or Docker on their own machine to get the apps or the server image.

| What | Workflow | When | Result |
|---|---|---|---|
| Server image (backend + web app), amd64 and arm64 | `docker.yml` | every push to `main` | `ghcr.io/<owner>/familienhub:edge` |
| | | tag `v1.2.3` | `:1.2.3`, `:1.2`, `:latest` |
| | | tag `v1.2.3-beta.1` | `:1.2.3-beta.1`, `:beta` |
| Android APK, iOS IPA, `docker-compose.yml` | `release.yml` | tag `v*` | GitHub release with the files and `SHA256SUMS.txt` (tags with `-` become pre-releases) |
| iOS IPA only | `ios.yml` | push to `main` touching `app/`, or by hand | workflow artifact (14 days) |
| Tests | `ci.yml` | every push and PR | – |

## Make a release

1. Set the version in `app/pubspec.yaml` (`version: 1.2.3+1`; the build number is computed from the commit count).
2. Merge to `main`.
3. Tag and push: `git tag v1.2.3 && git push origin v1.2.3` (pre-release: `v1.2.3-beta.1`).
   `release.yml` stops if the tag does not match the version in `pubspec.yaml`.

## Repository secrets for the Android app

Under *Settings → Secrets and variables → Actions*. All are optional.

| Secret | Purpose |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | Your release keystore, `base64 -w0 release.jks` |
| `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD` | Its passwords and alias |
| `GOOGLE_SERVICES_JSON` | Content of `google-services.json` from your Firebase project, for push in the Android app |

- **Without a keystore** the APK is signed with a throwaway debug key. It installs fine, but the next release cannot update it; people would have to uninstall first. Keep the same keystore for all releases. If you lose it, nobody can update.
- **Without Firebase** the app works, and notifications go through ntfy or Web Push. Firebase push only works with a hub that has the service account of *the same* Firebase project (`FCM_SERVICE_ACCOUNT_FILE`), so for a public APK, ntfy is the channel that works for everyone.

## iOS

The IPA is unsigned. People install it with [SideStore](https://sidestore.io/) or [Sideloadly](https://sideloadly.io/) and a free Apple ID; the signature lasts 7 days and SideStore renews it on the phone. A signed build (TestFlight) and iOS push via APNs need a paid Apple developer account; see the [roadmap](roadmap.md).

## Visibility

Images in GitHub Container Registry inherit the repository's visibility on first push. While the repository is private, `docker compose pull` needs `docker login ghcr.io` with a token that has `read:packages`. After making the repository public, also set the package to public (*Packages → familienhub → Package settings → Change visibility*).
