# Upload MARGINAL through the GitHub browser

This folder is ready for `SignalLayerLabs/Marginal`.

## Replace the repository contents

1. Open `https://github.com/SignalLayerLabs/Marginal`.
2. Delete the previous files, or use a new empty repository if preferred.
3. Extract the ZIP locally.
4. On macOS press `Command + Shift + .` in Finder to display the hidden `.github` folder.
5. Upload every item inside the `Marginal` folder, including `.github`, to the repository root.
6. Use this commit message:

   `fix: publish verified MARGINAL v0.1.0 source`

## Expected automatic workflows

The initial upload starts only:

- CI on Python 3.10, 3.11, 3.12 and 3.13;
- CodeQL.

The Release and Killer Demo Pages workflows are manual by design, so they do not fail before setup is complete.

## Publish the release

After CI is green:

1. Open **Actions**.
2. Select **Release**.
3. Select **Run workflow** on `main`.

The workflow builds and attaches the wheel and source distribution to release `v0.1.0`.

## Publish the Killer Demo

1. Open **Settings → Pages**.
2. Set **Source** to **GitHub Actions**.
3. Open **Actions → Killer Demo Pages**.
4. Select **Run workflow** on `main`.
