# Toy Story 3 CSV Translator — Android project

This is an Android/Kivy port of the desktop CSV translator. It is not a prebuilt APK.
The GitHub Actions workflow builds a debug APK and uploads it as a workflow artifact.

## Features
- Load and save CSV with the required columns (`index`, `file_offset_hex`, `byte_length`, `raw_hex`, `translation`).
- Preserves headers, row order, and other columns when saving.
- Translates one entry or all entries using Google's unofficial public translation endpoint.
- Protects common placeholders/tags before translation.
- Edit entries and inspect placeholder differences.

## Build APK with GitHub Actions
1. Create a new GitHub repository.
2. Upload the contents of this folder to the repository root (not the ZIP itself).
3. Open **Actions** and select **Build Android APK**.
4. Click **Run workflow** (or push to `main`/`master`).
5. Wait for the workflow to finish successfully.
6. Open the completed workflow run, find **Artifacts**, and download `ToyStory3-CSV-Translator-APK`.
7. Extract the downloaded artifact ZIP; it contains the `.apk`.

## Important
- The APK is not yet compiled or device-tested here.
- Translation requires an internet connection. The Google endpoint is unofficial and may rate-limit requests.
- Android file access differs by Android version. If the file picker does not return a usable path, use a file manager to copy the CSV to an accessible folder and enter its path.
- This version uses a simple editor view and does not reproduce every detail of the desktop Tkinter interface.
