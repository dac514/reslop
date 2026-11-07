# Publishing on renoise.com

Tools are published by uploading the file from `just package` at
https://www.renoise.com/submit/tool. The rules below come from that page and from a
moderator in https://forum.renoise.com/t/editing-tools-on-the-site/79811 .

- The site matches an upload by the manifest `<Id>`. A known Id adds a new version to that
  tool, and an unknown Id creates a new tool. The page does not say what happens when the
  version is already there, so upload each `<Version>` once.
- The `.xrnx` must be 16 MB or smaller. Its uncompressed size must be at most 8 times that.
- The tool page shows the `README.md` at the root of the archive, or the file that
  `<DocumentationPath>` names. That file is the page, so keep it as the user guide.
- `<Description>` is shown only in the list at https://www.renoise.com/tools, cut at 120
  characters. The description you can edit on the site is also only for that list.
- The images come from the root of the archive: `cover.png` for the tool page and
  `thumbnail.png` for the list. Only PNG is allowed. `<CoverPath>` and `<ThumbnailPath>` in
  the manifest can name other files. Keep the images in the archive: in November 2026,
  images changed on the site after an upload did not always stick.
- The site resizes covers to 600x350 and stretches them if needed, so a tall dialog
  screenshot comes out squashed. Draw the cover at 600x350 and keep the screenshot's
  proportions.
- Draw the thumbnail at 120x45, the size the site serves. The submit page says 125x45, but
  every thumbnail on the site is 120x45.
- `just package` ships every file in the bundle except `dev/` and `preferences.xml`, so
  images at the bundle root need no extra step. The template ships no images on purpose,
  because placeholder images would end up on the site.
- Before uploading, run `unzip -l dist/<Id>.xrnx` and check that `cover.png`,
  `thumbnail.png` and `README.md` are at the root.
