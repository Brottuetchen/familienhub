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

## Publishing a beta (e.g. v1.0.0-beta.2)

Before publishing:

1. Verify that the latest `main` CI and iOS build are green. A successful Docker image workflow on `main` publishes `:edge`, **not** `:latest`.
2. **Required:** configure the Android signing secrets in **Settings → Secrets and variables → Actions** before publishing. The release workflow refuses to build a public APK without them. Without the same permanent signing key on each release, users cannot install APK updates in place. Back up the keystore and its password securely outside GitHub. Do not add them to the repository.
3. If you need native Firebase push in the public Android app, configure `GOOGLE_SERVICES_JSON` using the same Firebase project as the server; otherwise prefer ntfy/Web Push as documented.
4. Confirm the GHCR image package is **public** (repository visibility does not guarantee package visibility).
5. Add the version's section to [`CHANGELOG.md`](../CHANGELOG.md) (`## [1.0.0-beta.2]`). The release workflow copies that section into the GitHub release notes.
6. GitHub is the primary repository. Do not push to it from a mirror: a push mirror with pruning overwrites `main` and deletes branches and tags.

Either way works:

- **In the browser, no Git needed:** *Releases → Draft a new release → Choose a tag*. Type `v1.0.0-beta.2`, choose *Create new tag on publish* and target `main`. Tick *Set as a pre-release*, then *Publish release*. The new tag starts the workflows. The release workflow then attaches the APK, IPA, compose file and checksums to this release and replaces its notes with the CHANGELOG section.
- **With Git:** push a tag. The workflow then creates the release itself:

```bash
git status --short
git remote -v
git tag -a v1.0.0-beta.2 -m "Familienhub 1.0.0-beta.2"
git push origin v1.0.0-beta.2
```

The tag must point at a commit whose `app/pubspec.yaml` version is `1.0.0+1` (or another build number with the same `1.0.0` version). After pushing, wait for both the **Release** and **Docker image** GitHub Actions workflows to complete. The release job uploads an Android APK, unsigned iOS IPA, checksums, and a **release-pinned** `docker-compose.yml`.

Verify the image and installation from a clean machine before announcing the beta:

```bash
docker pull ghcr.io/brottuetchen/familienhub:1.0.0-beta.2
# Use the docker-compose.yml attached to the GitHub release,
# or override the default image tag with FAMILIENHUB_VERSION.
FAMILIENHUB_VERSION=1.0.0-beta.2 docker compose up -d
```

Important: the iOS IPA is **unsigned** and must be signed by the installer's Apple ID; it is not a TestFlight/App Store build. Without APNs entitlements, use the PWA with Web Push or the ntfy app. Beta users should expect issues and report them via the issue templates.

### Afterwards

- Bump the [Home Assistant add-on](https://github.com/Brottuetchen/familienhub-ha-addon) to the new image tag (its README lists the steps).
- The stable `v1.0.0` tag should follow real external-installation tests, not just successful CI.

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
